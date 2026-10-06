"""
Потенциальные клиенты и рассылки по базе (savdex/crm/prospects.py,
savdex/crm/prospects_admin.py).

- запись с неполными данными (физлицо с одним телефоном) заводится, в
  списке пустое — «—»; повтор по телефону — ошибка формы со ссылкой;
- загрузка Excel: образец читается целиком, повторы склеиваются (по ИНН,
  телефону, почте), повторная загрузка ничего не удваивает, пустая
  ячейка не стирает, компания с площадки отмечается, строка без всего —
  в отчёт, кривая почта — заметка;
- письмо отмеченным: окно с охватом, «все по отбору», очередь, фоновый
  проход (manage.py notify) — письмо с метками и ссылкой «отписаться»,
  счётчик +1; без почтовика — не отправляется;
- отметка вручную — счётчик +1 у всех отмеченных;
- «В лиды» — лид «Холодный контакт», запись с отметкой, дважды — нет;
- отписка: открытие ссылки не отписывает, кнопка — да, чужой ключ — 404;
- права: продажи работают с базой, модератор — нет.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL) — кроме проверок без базы.
"""

from __future__ import annotations

import io
import re
import subprocess
import sys
from email import message_from_string
from email.header import decode_header, make_header
from urllib.parse import urlencode

import pytest

from savdex.crm import prospects
from savdex.tenders import importer

from .pg_admin import (
    PYTHON,
    ОКРУЖЕНИЕ,
    django,
    sql,
    журнал,
    нужна_база,
    свежая_база,
    сотрудник,
    файл,
)

LIST = "/py/admin/crm/prospect/"
SMTP = {"MAIL_MAILER": "smtp"}

# ── Без базы ────────────────────────────────────────────────────────


def test_кто_это():
    assert prospects.kind_of("Физ. лицо") == "person"
    assert prospects.kind_of("ФРИЛАНСЕР") == "freelancer"
    assert prospects.kind_of("Юридическое лицо") == "company"
    assert prospects.kind_of("непонятно") is None
    assert prospects.kind_of("") is None


def test_ключи_склейки():
    assert prospects.keys({"tin": "301 234 567", "phone": "+998 90 123-45-67, 71 200-00-00"}) == [
        "t:301234567",
        "p:901234567",
    ]
    assert prospects.keys({"phone": "8 (90) 123 45 67"}) == ["p:901234567"]
    assert prospects.keys({"email": " Info@Mebel.UZ "}) == ["e:info@mebel.uz"]
    # Ни ИНН, ни телефона, ни почты — по названию и контакту
    assert prospects.keys({"name": "Иванов Сергей", "contact_person": None}) == ["n:иванов сергей|"]
    assert prospects.keys({}) == []


def test_образец_читается_загрузкой():
    table = importer.read_table("sample.xlsx", prospects.sample_workbook())
    mapping = prospects.column_map(table[0].keys())

    assert set(mapping) == {c.name for c in prospects.COLUMNS}
    assert len(table) == len(prospects.SAMPLE_ROWS)


def test_заголовки_на_других_языках():
    mapping = prospects.column_map(
        ["Kompaniya", "Telefon", "E-mail", "ФИО", "Сфера", "Комментарий"]
    )

    assert mapping == {
        "name": "Kompaniya",
        "phone": "Telefon",
        "email": "E-mail",
        "contact_person": "ФИО",
        "industry": "Сфера",
        "note": "Комментарий",
    }


# ── С базой ─────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    return {role: сотрудник(role) for role in ("superadmin", "admin", "sales", "moderator")}


@pytest.fixture
def чисто(люди) -> None:
    sql("delete from crm_prospect_mailing_recipients")
    sql("delete from crm_prospect_mailings")
    sql("delete from crm_prospects")
    sql("delete from crm_leads")
    sql("delete from admin_actions")


def _xlsx(rows: list[list[object]]) -> bytes:
    from openpyxl import Workbook

    book = Workbook()
    sheet = book.active
    assert sheet is not None

    for row in rows:
        sheet.append(row)

    buffer = io.BytesIO()
    book.save(buffer)

    return buffer.getvalue()


def _завести(**поля: object) -> int:
    names = list(поля)
    [(pk,)] = sql(
        f"insert into crm_prospects ({', '.join(names)}, created_at, updated_at) "
        f"values ({', '.join(['%s'] * len(names))}, now(), now()) returning id",
        list(поля.values()),
    )

    return int(pk)


def _загрузить(uid: int, content: bytes, **поля: str) -> dict:
    _, ответ = django(
        uid,
        ("post", LIST + "import/", {"file": файл("база.xlsx", content), **поля}),
    )
    assert ответ["status"] == 200, ответ["body"][:1500]

    return ответ


@нужна_база
def test_неполные_данные_и_дубль(люди, чисто):
    _, создано, дубль, список = django(
        люди["sales"],
        ("post", LIST + "add/", {"phone": "+998 93 765-43-21", "kind": "person"}),
        ("post", LIST + "add/", {"name": "Другой", "phone": "93 765 43 21"}),
        ("get", LIST, None),
    )

    assert создано["status"] == 302, создано["body"][:1500]
    assert "Такой уже есть в базе" in дубль["body"]
    [(name, kind, phone, created_by)] = sql(
        "select name, kind, phone, created_by from crm_prospects"
    )
    assert (name, kind, phone, created_by) == (None, "person", "+998 93 765-43-21", люди["sales"])
    assert "+998 93 765-43-21" in список["body"]
    assert "Физлицо" in список["body"]
    assert список["body"].count("—") >= 5, "пустые поля видны как «—»"
    assert журнал("created")["section"] == "prospects"


@нужна_база
def test_поиск_по_телефону(люди, чисто):
    _завести(name="Мебель Плюс", phone="+998 (90) 123-45-67, 71 200-00-00")
    _завести(name="Стройбаза", phone="+998 93 765 43 21")

    for запрос in ("901234567", "90 123 45 67", "+998901234567"):
        _, ответ = django(люди["sales"], ("get", LIST + "?" + urlencode({"q": запрос}), None))

        assert "Мебель Плюс" in ответ["body"] and "Стройбаза" not in ответ["body"], запрос


@нужна_база
def test_только_название(люди, чисто):
    """Без «кто это» — пусто (NULL), а не пустая строка поперёк проверки базы."""
    _, ответ = django(люди["sales"], ("post", LIST + "add/", {"name": "Ферганский цемент"}))

    assert ответ["status"] == 302, ответ["body"][:1500]
    assert sql("select kind, tin, email from crm_prospects") == [(None, None, None)]


@нужна_база
def test_пустую_запись_не_завести(люди, чисто):
    _, ответ = django(люди["sales"], ("post", LIST + "add/", {"city": "Ташкент"}))

    assert "Заполните хотя бы одно" in ответ["body"]
    assert sql("select count(*) from crm_prospects") == [(0,)]


@нужна_база
def test_загрузка_и_повтор(люди, чисто):
    sql(
        "insert into companies (name, slug, tin, status, created_at, updated_at) values "
        "('Мебель Плюс', 'mebel-plus', '301234567', 'active', now(), now())"
    )
    [(company,)] = sql("select id from companies where tin = '301234567'")
    шапка = ["Название / ФИО", "Кто это", "ИНН", "Контактное лицо", "Телефон", "Почта", "Город"]
    файл_1 = _xlsx(
        [
            шапка,
            ["ООО «МЕБЕЛЬ ПЛЮС»", "Компания", "301 234 567", "Азиз", "+998 90 123-45-67",
             "info@mebelplus.uz", "Ташкент"],
            ["Иванов Сергей", "Физ. лицо", None, None, "+998 93 765-43-21", "не почта", None],
            ["Дилноза", "фрилансер", "", "", "", "dilnoza@gmail.com", ""],
            # Та же компания ещё раз — по телефону, внутри файла
            ["Мебель Плюс", None, None, None, "90 123 45 67", None, "Самарканд"],
            [None, None, None, None, None, None, "Бухара"],
        ]
    )  # fmt: skip

    ответ = _загрузить(люди["sales"], файл_1, source="Выставка UzBuild 2026")

    assert "Новых: <b>3</b>" in ответ["body"], ответ["body"][:3000]
    assert "повторов внутри файла: <b>1</b>" in ответ["body"]
    assert "нет ни названия, ни контактного лица" in ответ["body"], "строка без всего — в отчёт"
    assert "не похожа на адрес" in ответ["body"]
    rows = sql(
        "select name, kind, tin, email, city, source, company_id from crm_prospects order by id"
    )
    assert rows == [
        # Повтор внутри файла дополнил первую строку: непустое — новее
        ("Мебель Плюс", "company", "301234567", "info@mebelplus.uz", "Самарканд",
         "Выставка UzBuild 2026", company),
        ("Иванов Сергей", "person", None, None, None, "Выставка UzBuild 2026", None),
        ("Дилноза", "freelancer", None, "dilnoza@gmail.com", None, "Выставка UzBuild 2026", None),
    ]  # fmt: skip
    assert "строк 5, новых 3" in (
        sql("select note from admin_actions where action = 'imported'")[0][0] or ""
    )

    # Повторно — с новым городом у одного и пустыми ячейками у другого
    sql("update crm_prospects set mailings_count = 2")
    файл_2 = _xlsx(
        [
            шапка,
            ["Мебель Плюс", None, "301234567", None, None, None, None],
            ["Иванов Сергей", None, None, None, "+998937654321", None, "Наманган"],
        ]
    )
    ответ = _загрузить(люди["sales"], файл_2, source="Другой файл")

    assert "Новых: <b>0</b>" in ответ["body"]
    assert "обновлено: <b>1</b>" in ответ["body"] and "без изменений: <b>1</b>" in ответ["body"]
    assert sql("select count(*) from crm_prospects") == [(3,)]
    assert sql("select city, source, mailings_count from crm_prospects order by id") == [
        ("Самарканд", "Выставка UzBuild 2026", 2),
        ("Наманган", "Выставка UzBuild 2026", 2),
        (None, "Выставка UzBuild 2026", 2),
    ], "пустая ячейка не стирает, «откуда» — первое, счётчик не сбрасывается"

    # Заметка дописывается к прежней; та же ещё раз — не дублируется
    for заметка in ("Звонить в марте", "Ждут прайс", "Ждут прайс"):
        _загрузить(люди["sales"], _xlsx([["ИНН", "Заметка"], ["301234567", заметка]]))

    assert sql("select note from crm_prospects where tin = '301234567'") == [
        ("Звонить в марте\nЖдут прайс",)
    ]


@нужна_база
def test_вкладки_и_отбор(люди, чисто):
    _завести(name="Новый", email="a@a.uz")
    _завести(name="Писали", email="b@b.uz", mailings_count=2)
    _завести(name="Не писать", email="c@c.uz", unsubscribed_at="2026-10-01")

    _, все, писали = django(
        люди["sales"], ("get", LIST, None), ("get", LIST + "?state=mailed", None)
    )

    assert "Ещё не писали <b>1</b>" in все["body"] and "Не писать <b>1</b>" in все["body"]
    assert "Писали" in писали["body"] and "a@a.uz" not in писали["body"]


@нужна_база
def test_письмо_очередь_и_отправка(люди, чисто, tmp_path):
    с_почтой = _завести(name="Мебель Плюс", contact_person="Азиз", email="aziz@mebel.uz")
    без_контакта = _завести(name="Стройбаза", email="info@stroy.uz", kind="company")
    без_почты = _завести(name="Иванов", phone="+998901112233")
    отписался = _завести(name="Нет", email="no@no.uz", unsubscribed_at="2026-10-01")
    в_лидах = _завести(name="Лид", email="lead@lead.uz", converted_at="2026-10-01")
    все = [с_почтой, без_контакта, без_почты, отписался, в_лидах]
    выбор = {"action": "send_email", "index": "0", "_selected_action": все}

    _, окно, отправлено = django(
        люди["sales"],
        ("post", LIST, выбор),
        (
            "post",
            LIST,
            {
                **выбор,
                "post": "yes",
                "subject": "Здравствуйте, {имя}",
                "body": "Приглашаем {компания} на SavdEx: https://savdex.uz/register",
                "reply_to": "sales@savdex.uz",
            },
        ),
        env=SMTP,
    )

    assert "Письмо получат: <b>2</b>" in окно["body"], окно["body"][:3000]
    assert "Не получат: без почты — 1, «не писать» — 1, уже в лидах — 1." in окно["body"]
    assert отправлено["status"] == 302, отправлено["body"][:2000]
    assert "/py/admin/crm/prospectmailing/" in отправлено["location"]
    assert sql(
        "select prospect_id, status from crm_prospect_mailing_recipients order by prospect_id"
    ) == [(с_почтой, "queued"), (без_контакта, "queued")]
    assert журнал("sent")["subject_label"] == "Здравствуйте, {имя}"

    # Фоновый проход: письма в файл журнала почты
    почта = tmp_path / "mail.log"
    проход = subprocess.run(
        [sys.executable, "manage.py", "notify", "--once"],
        cwd=PYTHON,
        env={
            **ОКРУЖЕНИЕ,
            "DJANGO_SETTINGS_MODULE": "savdex.settings",
            "MAIL_MAILER": "log",
            "MAIL_LOG_PATH": str(почта),
            "APP_URL": "https://savdex.uz",
        },
        capture_output=True,
        text=True,
    )
    assert проход.returncode == 0, проход.stderr[-2000:]
    письма = почта.read_text(encoding="utf-8")

    assert "To: aziz@mebel.uz" in письма and "To: info@stroy.uz" in письма
    assert "no@no.uz" not in письма and "lead@lead.uz" not in письма
    assert "Reply-To: sales@savdex.uz" in письма
    # Длинный заголовок почта переносит на следующую строку
    assert re.search(r"List-Unsubscribe:\s+<https://savdex\.uz/unsubscribe/\d+/\w{32}>", письма)
    assert "List-Unsubscribe-Post: List-Unsubscribe=One-Click" in письма
    assert sql("select status from crm_prospect_mailing_recipients") == [("sent",), ("sent",)]
    assert sql(
        "select id, mailings_count, last_mailed_at is not null from crm_prospects "
        "where mailings_count > 0 order by id"
    ) == [(с_почтой, 1, True), (без_контакта, 1, True)]
    assert sql(
        "select total, sent, failed, finished_at is not null from crm_prospect_mailings"
    ) == [(2, 2, 0, True)]

    # Метки: {имя} — контактное лицо, у кого его нет — название
    темы = sorted(
        str(make_header(decode_header(message_from_string(chunk)["Subject"])))
        for chunk in re.split(r"(?m)^(?=Content-Type: multipart/alternative)", письма)
        if chunk.strip()
    )
    assert темы == ["Здравствуйте, Азиз", "Здравствуйте, Стройбаза"]


@нужна_база
def test_метки_письма(люди, чисто):
    """Тема и текст письма: метки из записи, ссылка «отписаться» в конце."""
    from savdex.crm.models import Prospect, ProspectMailing

    письмо = ProspectMailing(
        subject="Здравствуйте, {имя}", body="Для {компания}\n\nhttps://savdex.uz"
    )
    тема, страница, текст = prospects.render(
        письмо, Prospect(pk=7, name="Стройбаза", contact_person=None)
    )

    assert тема == "Здравствуйте, Стройбаза"
    assert текст.startswith("Для Стройбаза\n\nhttps://savdex.uz")
    assert "/unsubscribe/7/" + prospects.unsubscribe_token(7) in текст
    assert '<a href="https://savdex.uz">https://savdex.uz</a>' in страница
    assert prospects.render(письмо, Prospect(pk=8))[0] == "Здравствуйте, коллеги"


@нужна_база
def test_без_почтовика_не_отправить(люди, чисто):
    pk = _завести(name="Мебель Плюс", email="aziz@mebel.uz")
    выбор = {"action": "send_email", "index": "0", "_selected_action": [pk]}

    _, ответ = django(
        люди["sales"],
        ("post", LIST, {**выбор, "post": "yes", "subject": "Тема", "body": "Текст"}),
        # На боевом почтовик «log» — не почта: письма легли бы в файл
        env={"MAIL_MAILER": "log", "APP_ENV": "production"},
    )

    assert "Почта площадки ещё не настроена" in ответ["body"]
    assert sql("select count(*) from crm_prospect_mailings") == [(0,)]


@нужна_база
def test_все_по_отбору(люди, чисто):
    """«Выбрать все» — весь отбор на всех страницах, а не только видимые."""
    for n in range(130):
        _завести(name=f"Компания {n}", email=f"c{n}@x.uz")

    _завести(name="Писали", email="w@x.uz", mailings_count=1)

    _, окно = django(
        люди["sales"],
        (
            "post",
            LIST + "?" + urlencode({"state": "new"}),
            {"action": "send_email", "index": "0", "select_across": "1", "_selected_action": ["1"]},
        ),
        env=SMTP,
    )

    assert "Отмечено: <b>130</b>" in окно["body"], окно["body"][:3000]
    assert 'name="select_across" value="1"' in окно["body"]

    # Подтверждение из окна — тоже весь отбор, а не одна отмеченная строка
    _, отмечено = django(
        люди["sales"],
        (
            "post",
            LIST + "?" + urlencode({"state": "new"}),
            {
                "action": "mark_mailing",
                "index": "0",
                "select_across": "1",
                "_selected_action": ["1"],
                "post": "yes",
                "channel": "call",
            },
        ),
    )

    assert отмечено["status"] == 302, отмечено["body"][:2000]
    assert sql(
        "select count(*) from crm_prospects where name like 'Компания %%' and mailings_count = 1"
    ) == [(130,)]
    assert sql("select mailings_count from crm_prospects where name = 'Писали'") == [(1,)]


@нужна_база
def test_отметка_вручную(люди, чисто):
    a = _завести(name="А", phone="+998901112233")
    b = _завести(name="Б", email="b@b.uz", mailings_count=3)

    _, ответ = django(
        люди["sales"],
        (
            "post",
            LIST,
            {
                "action": "mark_mailing",
                "index": "0",
                "_selected_action": [a, b],
                "post": "yes",
                "channel": "telegram",
                "note": "Прайс на 2027",
            },
        ),
    )

    assert ответ["status"] == 302
    assert sql("select id, mailings_count from crm_prospects order by id") == [(a, 1), (b, 4)]
    assert sql("select channel, note, total, sent from crm_prospect_mailings") == [
        ("telegram", "Прайс на 2027", 2, 2)
    ]
    _, карточка = django(люди["sales"], ("get", f"{LIST}{a}/change/", None))
    assert "Прайс на 2027" in карточка["body"] and "Telegram" in карточка["body"]


@нужна_база
def test_в_лиды(люди, чисто):
    a = _завести(
        name="Мебель Плюс", tin="301234567", contact_person="Азиз",
        phone="+998 90 123-45-67, +998 71 200-00-00", email="aziz@mebel.uz",
        city="Ташкент", mailings_count=2,
    )  # fmt: skip
    b = _завести(name="Иванов", kind="person", phone="+998931112233")

    _, один, массово, ещё_раз = django(
        люди["sales"],
        ("post", f"{LIST}{a}/to-lead/", {}),
        ("post", LIST, {"action": "to_leads", "index": "0", "_selected_action": [a, b]}),
        ("post", f"{LIST}{a}/to-lead/", {}),
    )

    assert один["status"] == 302 and "/py/admin/crm/lead/" in один["location"]
    assert массово["status"] == 302
    leads = sql(
        "select title, source, contact_name, contact_phone, contact_email, owner_id, status, note "
        "from crm_leads order by id"
    )
    assert len(leads) == 2, "второй раз в лиды не уходит"
    title, source, name, phone, email, owner, status, note = leads[0]
    assert (title, source, name, phone, email, owner, status) == (
        "Мебель Плюс",
        "outbound",
        "Азиз",
        "+998 90 123-45-67",
        "aziz@mebel.uz",
        люди["sales"],
        "new",
    )
    assert "ИНН: 301234567" in note and "Рассылок: 2" in note
    assert sql("select count(*) from crm_prospects where lead_id is not null") == [(2,)]
    assert ещё_раз["location"] == f"{LIST}{a}/change/", "уже в лидах — назад к записи"
    assert журнал("created")["section"] == "leads"


@нужна_база
def test_отписка(люди, чисто):
    pk = _завести(name="Мебель Плюс", email="aziz@mebel.uz")
    [(mailing,)] = sql(
        "insert into crm_prospect_mailings (channel, subject, total, created_at, updated_at) "
        "values ('email', 'Тема', 1, now(), now()) returning id"
    )
    sql(
        "insert into crm_prospect_mailing_recipients (mailing_id, prospect_id, status) "
        "values (%s, %s, 'queued')",
        [mailing, pk],
    )
    адрес = f"/unsubscribe/{pk}/{_token(pk)}"
    чужой = f"/unsubscribe/{pk}/{'0' * 32}"

    _, открыл, чужая = django(люди["sales"], ("get", адрес, None), ("get", чужой, None))

    assert открыл["status"] == 200 and "Отписаться" in открыл["body"]
    assert sql("select unsubscribed_at from crm_prospects") == [(None,)], "открытие не отписывает"
    assert чужая["status"] == 404

    _, нажал = django(люди["sales"], ("post", адрес, {"List-Unsubscribe": "One-Click"}))

    assert нажал["status"] == 200 and "больше не напишем" in нажал["body"]
    assert sql("select unsubscribed_at is not null from crm_prospects") == [(True,)]
    assert sql("select status, error from crm_prospect_mailing_recipients") == [
        ("skipped", "отписался")
    ]


def _token(pk: int) -> str:
    """Ключ отписки — как у Django в процессе проверки (тот же APP_KEY)."""
    вывод = subprocess.run(
        [
            sys.executable,
            "-c",
            "import django; django.setup(); from savdex.crm import prospects; "
            f"print(prospects.unsubscribe_token({pk}))",
        ],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "DJANGO_SETTINGS_MODULE": "savdex.settings", "PYTHONPATH": str(PYTHON)},
        capture_output=True,
        text=True,
    )
    assert вывод.returncode == 0, вывод.stderr[-2000:]

    return вывод.stdout.strip()


@нужна_база
def test_остановить_рассылку(люди, чисто):
    pk = _завести(name="Мебель Плюс", email="aziz@mebel.uz")
    [(mailing,)] = sql(
        "insert into crm_prospect_mailings (channel, subject, total, created_at, updated_at) "
        "values ('email', 'Тема', 1, now(), now()) returning id"
    )
    sql(
        "insert into crm_prospect_mailing_recipients (mailing_id, prospect_id, status) "
        "values (%s, %s, 'queued')",
        [mailing, pk],
    )
    url = f"/py/admin/crm/prospectmailing/{mailing}/"

    _, страница, стоп = django(
        люди["sales"], ("get", url + "change/", None), ("post", url + "stop/", {})
    )

    assert "Остановить рассылку" in страница["body"]
    assert стоп["status"] == 302
    assert sql("select status from crm_prospect_mailing_recipients") == [("skipped",)]
    assert sql("select finished_at is not null from crm_prospect_mailings") == [(True,)]


@нужна_база
def test_права(люди, чисто):
    pk = _завести(name="Мебель Плюс")

    _, модератор = django(люди["moderator"], ("get", LIST, None))
    _, продажи = django(люди["sales"], ("get", LIST, None))
    _, админ = django(люди["admin"], ("get", LIST, None))
    _, удалить = django(
        люди["sales"],
        ("post", LIST, {"action": "delete_selected", "index": "0", "_selected_action": [pk]}),
    )

    assert модератор["status"] == 403
    assert продажи["status"] == 200 and "Загрузить из Excel" in продажи["body"]
    assert 'value="delete_selected"' not in продажи["body"], "удалять продажам нельзя"
    assert 'value="delete_selected"' in админ["body"]
    assert sql("select deleted_at from crm_prospects") == [(None,)]
    assert удалить["status"] in (200, 302)
