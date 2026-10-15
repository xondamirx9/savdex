"""
Регистрация в ILMORA через Savdex (savdex/ilmora).

- проверка каждого поля: телефон, ФИО, тип лица, ПИНФЛ и ИНН (меньше и
  больше цифр, буквы, одна цифра 14 раз), обе галочки оферты — понятная
  причина под полем;
- заявка физлица и юрлица ложится в ilmora_registrations: телефон
  +998XXXXXXXXX, ФИО без лишних пробелов, время обеих галочек; аккаунт
  Savdex не заводится, вход не выполняется; после — «Заявка принята»;
- ограничение частоты формы;
- раздел админки: видят суперадмин и администратор, остальным — отказ;
  повторы по телефону и номеру помечены, выгрузка — по праву ilmora.export.

Проверки полей базы не требуют; остальное — PostgreSQL (SAVDEX_PARITY_PG_URL).
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from typing import Any

import pytest

from savdex import access, laravel_session
from savdex.ilmora.form import validate
from savdex.web import ui

from .pg_admin import django, sql, нужна_база, свежая_база, сотрудник
from .test_web_forms import inertia, отправить
from .web_site import адрес, открыть, страница

PATH = "/register/ilmora-register"
IP = "192.0.2.211"

ВЕРНО = {
    "phone": "99 222 33 44",
    "full_name": "  Алиев   Вали  Каримович ",
    "person_type": "individual",
    "pinfl": "31234567890123",
    "offer_read": True,
    "offer_sign": True,
}


class _Язык:
    """Контекст для проверки полей: только язык и словарь."""

    def __init__(self, locale: str = "ru") -> None:
        self.locale = locale

    def t(self, key: str, **replace: object) -> str:
        return ui.t(key, self.locale, **replace)


def _ошибки(locale: str = "ru", **поля: Any) -> dict[str, list[str]]:
    _, errors = validate(_Язык(locale), {**ВЕРНО, **поля})  # type: ignore[arg-type]

    return errors


# ── Поля ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("phone", "ошибка"),
    [
        ("", "Укажите номер телефона"),
        ("99 222 33 4", "После +998 нужно 9 цифр — введено 8"),
        ("99 222 33 445", "После +998 нужно 9 цифр — введено 10"),
        ("99 abc 33 44", "В номере телефона — только цифры"),
    ],
)
def test_телефон_с_ошибкой(phone, ошибка):
    assert _ошибки(phone=phone) == {"phone": [ошибка]}


@pytest.mark.parametrize(
    "phone", ["992223344", "+998 99 222 33 44", "998992223344", "(99) 222-33-44"]
)
def test_телефон_верный(phone):
    заявка, errors = validate(_Язык(), {**ВЕРНО, "phone": phone})  # type: ignore[arg-type]

    assert errors == {} and заявка is not None and заявка.phone == "+998992223344"


@pytest.mark.parametrize(
    ("name", "ошибка"),
    [
        ("", "Укажите фамилию, имя и отчество"),
        ("   ", "Укажите фамилию, имя и отчество"),
        ("Алиев Вали", "Укажите фамилию, имя и отчество — не меньше трёх слов"),
        ("Алиев Вали 3", "В ФИО допустимы только буквы, апостроф и дефис"),
        ("Алиев Вали Карим!", "В ФИО допустимы только буквы, апостроф и дефис"),
        ("Алиев Вали -Карим", "В ФИО допустимы только буквы, апостроф и дефис"),
        ("Алиев Вали " + "к" * 150, "ФИО слишком длинное — не больше 150 знаков"),
    ],
)
def test_фио_с_ошибкой(name, ошибка):
    assert _ошибки(full_name=name) == {"full_name": [ошибка]}


@pytest.mark.parametrize(
    "name",
    [
        "Алиев Вали Каримович",
        "Алиев Вали Карим ўғли",
        "Aliyev Vali Karim oʻgʻli",
        "Toʻxtayev G‘ulom Qodir o’g’li",
        "Rahimova-Saidova Nodira Akmal qizi",
        "Ҳасанов Қодир Ғаниевич",
    ],
)
def test_фио_верное(name):
    assert _ошибки(full_name=name) == {}


def test_фио_без_лишних_пробелов():
    заявка, _ = validate(_Язык(), ВЕРНО)  # type: ignore[arg-type]

    assert заявка is not None and заявка.full_name == "Алиев Вали Каримович"


@pytest.mark.parametrize("kind", ["", "freelancer", None])
def test_тип_лица_обязателен(kind):
    assert _ошибки(person_type=kind) == {
        "person_type": ["Выберите: физическое или юридическое лицо"]
    }


@pytest.mark.parametrize(
    ("pinfl", "ошибка"),
    [
        ("", "Укажите ПИНФЛ"),
        ("3123456789012", "ПИНФЛ должен содержать 14 цифр — введено 13"),
        ("312345678901234", "ПИНФЛ должен содержать 14 цифр — введено 15"),
        ("3123456789012A", "ПИНФЛ — только цифры"),
        ("11111111111111", "Указан недействительный ПИНФЛ"),
    ],
)
def test_пинфл_с_ошибкой(pinfl, ошибка):
    assert _ошибки(pinfl=pinfl) == {"pinfl": [ошибка]}


@pytest.mark.parametrize(
    ("tin", "ошибка"),
    [
        ("", "Укажите ИНН"),
        ("3051234", "ИНН должен содержать 9 цифр — введено 7"),
        ("3051234567", "ИНН должен содержать 9 цифр — введено 10"),
        ("30512З456", "ИНН — только цифры"),
    ],
)
def test_инн_с_ошибкой(tin, ошибка):
    assert _ошибки(person_type="legal", pinfl="", tin=tin) == {"tin": [ошибка]}


def test_номер_по_типу_лица():
    """Физлицу ИНН не нужен, юрлицу — ПИНФЛ: проверяется только свой номер."""
    физ, _ = validate(_Язык(), {**ВЕРНО, "tin": "мусор"})  # type: ignore[arg-type]
    юр, _ = validate(
        _Язык(),  # type: ignore[arg-type]
        {**ВЕРНО, "person_type": "legal", "pinfl": "мусор", "tin": "305 123-456"},
    )

    assert физ is not None and (физ.pinfl, физ.tin) == ("31234567890123", None)
    assert юр is not None and (юр.pinfl, юр.tin) == (None, "305123456")


@pytest.mark.parametrize("значение", [False, None, "", "0", "no"])
def test_без_галочек(значение):
    assert _ошибки(offer_read=значение, offer_sign=значение) == {
        "offer_read": [
            "Подтвердите, что ознакомились с офертой и согласны на обработку персональных данных"
        ],
        "offer_sign": ["Подтвердите, что отметка — ваша подпись под заявлением"],
    }


def test_ошибки_по_узбекски():
    assert _ошибки("uz", person_type="legal", tin="3051234") == {
        "tin": ["STIR 9 ta raqamdan iborat bo‘lishi kerak — 7 ta kiritildi"]
    }


def test_тексты_только_на_двух_языках():
    """У ILMORA два языка: ключи — в русском и узбекском словарях, в en, tr и zh их нет."""

    def пути(узел: Any, путь: str = "") -> set[str]:
        if isinstance(узел, dict):
            return {п for k, v in узел.items() for п in пути(v, f"{путь}.{k}")}

        return {путь}

    русские = пути(ui.translations("ru")["ilmora"])

    assert пути(ui.translations("uz")["ilmora"]) == русские
    assert ui.translations("uz")["ilmora"] != ui.translations("ru")["ilmora"]

    for locale in ("en", "tr", "zh"):
        assert "ilmora" not in ui.translations(locale), locale


# ── Форма на сайте ──────────────────────────────────────────────────


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    with адрес() as root:
        yield root


def _счётчик_с_нуля() -> None:
    """Частота формы (throttle:10,10,ilmora-register) — с нуля для адреса IP."""
    from savdex import laravel_cache

    ключ = "ilmora-register" + hashlib.sha1(f"|{IP}".encode()).hexdigest()

    for имя in (ключ, ключ + ":timer"):
        laravel_cache.file_path(имя).unlink(missing_ok=True)


def _заявки() -> list[dict[str, Any]]:
    поля = (
        "person_type, phone, full_name, pinfl, tin, offer_accepted_at is not null, "
        "offer_signed_at is not null, offer_version, locale, ip, user_agent"
    )
    имена = [п.split(" ")[0] for п in поля.split(", ")]

    return [
        dict(zip(имена, строка, strict=True))
        for строка in sql(f"select {поля} from ilmora_registrations order by id")
    ]


def отправка(сайт: str, body: dict[str, Any], prefix: str = "", **окружение: str) -> dict[str, Any]:
    return отправить(
        сайт,
        prefix + PATH,
        lambda: None,
        _заявки,
        body=body,
        env={"CACHE_STORE": "file", **окружение},
        headers=inertia(
            Referer=сайт + prefix + PATH, **{"X-Forwarded-For": IP, "User-Agent": "ilmora-test"}
        ),
    )


@нужна_база
@pytest.mark.parametrize(
    ("body", "prefix", "строка"),
    [
        (
            ВЕРНО,
            "",
            {
                "person_type": "individual",
                "phone": "+998992223344",
                "full_name": "Алиев Вали Каримович",
                "pinfl": "31234567890123",
                "tin": None,
                "locale": "ru",
            },
        ),
        (
            {
                **ВЕРНО,
                "full_name": "Aliyev Vali Karim oʻgʻli",
                "person_type": "legal",
                "pinfl": "",
                "tin": "305123456",
            },
            "/uz",
            {
                "person_type": "legal",
                "phone": "+998992223344",
                "full_name": "Aliyev Vali Karim oʻgʻli",
                "pinfl": None,
                "tin": "305123456",
                "locale": "uz",
            },
        ),
    ],
)
def test_заявка_сохраняется(сайт, body, prefix, строка):
    sql("delete from ilmora_registrations")
    _счётчик_с_нуля()
    пользователей = sql("select count(*) from users")[0][0]

    итог = отправка(сайт, body, prefix)

    assert итог["ответ"]["headers"]["location"].endswith(prefix + PATH)
    assert итог["база"] == [
        {
            **строка,
            "offer_accepted_at": True,
            "offer_signed_at": True,
            "offer_version": "2026-10-15",
            "ip": IP,
            "user_agent": "ilmora-test",
        }
    ]
    # Аккаунт Savdex не заводится, вход не выполняется
    assert sql("select count(*) from users")[0][0] == пользователей
    сессия = json.loads(итог["сессия"]["payload"])
    assert laravel_session.LOGIN_KEY not in сессия
    assert сессия["ilmora"] == {"done": True}


@нужна_база
def test_без_капчи(сайт):
    """Капчи у ILMORA нет: заявка проходит и там, где капча входа включена."""
    sql("delete from ilmora_registrations")
    _счётчик_с_нуля()

    итог = отправка(сайт, ВЕРНО, CAPTCHA_ENABLED="true")

    assert len(итог["база"]) == 1
    данные = страница(открыть(сайт, PATH, env={"CAPTCHA_ENABLED": "true"})["body"])
    assert "captcha" not in данные["props"]


@нужна_база
def test_ошибки_под_полями(сайт):
    sql("delete from ilmora_registrations")
    _счётчик_с_нуля()

    итог = отправка(
        сайт,
        {
            "phone": "99 222",
            "full_name": "Алиев Вали",
            "person_type": "legal",
            "tin": "3051234",
            "offer_read": False,
        },
    )

    ошибки = json.loads(итог["сессия"]["payload"])["errors"]["default"]["messages"]
    assert ошибки == {
        "phone": ["После +998 нужно 9 цифр — введено 5"],
        "full_name": ["Укажите фамилию, имя и отчество — не меньше трёх слов"],
        "tin": ["ИНН должен содержать 9 цифр — введено 7"],
        "offer_read": [
            "Подтвердите, что ознакомились с офертой и согласны на обработку персональных данных"
        ],
        "offer_sign": ["Подтвердите, что отметка — ваша подпись под заявлением"],
    }
    assert итог["база"] == []


@нужна_база
def test_ограничение_частоты(сайт):
    sql("delete from ilmora_registrations")
    _счётчик_с_нуля()

    try:
        for _ in range(10):
            отправка(сайт, ВЕРНО)

        лишняя = отправка(сайт, ВЕРНО)
    finally:
        _счётчик_с_нуля()

    assert len(лишняя["база"]) == 10, "одиннадцатая заявка за 10 минут не сохраняется"
    ошибки = json.loads(лишняя["сессия"]["payload"])["errors"]["default"]["messages"]
    assert ошибки["body"][0].startswith("Слишком много действий подряд")


@нужна_база
@pytest.mark.parametrize(
    ("path", "язык", "заголовок"),
    [
        (PATH, "ru", "Регистрация в ILMORA"),
        ("/uz" + PATH, "uz", "ILMORAda ro‘yxatdan o‘tish"),
        # У ILMORA два языка: английская страница — по-русски
        ("/en" + PATH, "ru", "Регистрация в ILMORA"),
    ],
)
def test_страница_на_языке(сайт, path, язык, заголовок):
    ответ = открыть(сайт, path)
    данные = страница(ответ["body"])

    assert ответ["status"] == 200
    assert данные["component"] == "ilmora/Register"
    assert данные["props"]["locale"] == язык
    assert данные["props"]["translations"]["ilmora"]["title"] == заголовок
    assert данные["props"]["done"] is False
    assert данные["props"]["ilmoraUrl"] == "https://maftunashareef.github.io/ilmora-demo/"


@нужна_база
@pytest.mark.parametrize(
    ("path", "заголовок", "заявление"),
    [
        ("/ilmora/offer", "# ПУБЛИЧНАЯ ОФЕРТА", "# ЗАЯВЛЕНИЕ"),
        ("/uz/ilmora/offer", "# OMMAVIY OFERTA", "# ARIZA"),
    ],
)
def test_оферта_с_заявлением(сайт, path, заголовок, заявление):
    """Оферта и заявление на языке страницы; пустые места — метки, их заполняет браузер."""
    данные = страница(открыть(сайт, path)["body"])
    абзацы = данные["props"]["paragraphs"]
    текст = "\n".join(абзацы)

    assert данные["component"] == "ilmora/Offer"
    assert данные["props"]["version"] == "2026-10-15"
    assert абзацы[0] == заголовок and заявление in абзацы
    for метка in ("[ФИО]", "[НОМЕР_НАЗВАНИЕ]", "[НОМЕР]", "[ТЕЛЕФОН]", "[ДАТА]"):
        assert метка in текст, метка
    assert "[ОТМЕТКА_ОФЕРТА]" in текст and "[ОТМЕТКА_ПОДПИСЬ]" in текст
    # Редакция — 15.10.2026; процента посещаемости и пометок «уточнить» нет
    assert "«15»" in текст and "___ %" not in текст and "___ foiz" not in текст
    assert "уточнить" not in текст and "aniqlashtirish" not in текст


def test_тексты_галочек_как_в_оферте():
    """Галочки анкеты — дословно раздел 4.1 оферты (там же они в заявлении)."""
    from savdex.ilmora import views

    for locale in ("ru", "uz"):
        оферта = " ".join(views.offer_text(locale))
        анкета = ui.translations(locale)["ilmora"]
        ссылка = анкета["offer_link"]

        assert анкета["offer_read"].replace(":offer", ссылка) in оферта.replace(
            "публичной офертой", ссылка
        ).replace("ommaviy ofertasi", ссылка), locale
        assert анкета["offer_sign"] in оферта, locale


@нужна_база
def test_текст_оферты_из_файла(сайт, tmp_path, monkeypatch):
    """Абзацы — через пустую строку, пробелы внутри схлопываются, метки остаются."""
    from savdex.ilmora import views

    (tmp_path / "ru.txt").write_text("Я, [ФИО],  принимаю\nусловия.\n\n\nВторой абзац.\n")
    monkeypatch.setattr(views, "OFFER_DIR", tmp_path)

    assert views.offer_text("ru") == ["Я, [ФИО], принимаю условия.", "Второй абзац."]
    assert views.offer_text("en") == ["Я, [ФИО], принимаю условия.", "Второй абзац."]
    assert views.offer_text("uz") == []


# ── Админка ─────────────────────────────────────────────────────────

LIST = "/py/admin/ilmora/registration/"


def test_право_раздела():
    """ПИНФЛ — не всем: раздел видят суперадмин и администратор."""
    видят = {роль for роль in access.ROLES if "ilmora.view" in access.abilities_for(роль)}
    выгружают = {роль for роль in access.ROLES if "ilmora.export" in access.abilities_for(роль)}

    assert видят == выгружают == {"superadmin", "admin"}


def _заявка(**поля: Any) -> int:
    строка = {
        "person_type": "individual",
        "phone": "+998992223344",
        "full_name": "Алиев Вали Каримович",
        "pinfl": "31234567890123",
        "tin": None,
        "offer_accepted_at": "2026-10-01 10:00:00",
        "offer_signed_at": "2026-10-01 10:00:00",
        "offer_version": "draft",
        "locale": "uz",
        "ip": "203.0.113.5",
        "created_at": "2026-10-01 10:00:00",
        **поля,
    }
    [(pk,)] = sql(
        f"insert into ilmora_registrations ({', '.join(строка)}) "
        f"values ({', '.join(['%s'] * len(строка))}) returning id",
        list(строка.values()),
    )

    return int(pk)


@pytest.fixture(scope="module")
def люди(сайт) -> dict[str, int]:
    return {
        роль: сотрудник(роль)
        for роль in ("superadmin", "admin", "sales", "support", "moderator", "finance")
    }


@нужна_база
def test_кто_видит_раздел(люди):
    sql("delete from ilmora_registrations")
    _заявка()

    for роль in ("superadmin", "admin"):
        _, ответ = django(люди[роль], ("get", LIST, None))
        assert ответ["status"] == 200 and "Алиев Вали Каримович" in ответ["body"], роль

    for роль in ("sales", "support", "moderator", "finance"):
        _, список, выгрузка = django(
            люди[роль], ("get", LIST, None), ("get", LIST + "export/", None)
        )
        assert список["status"] == 403, роль
        assert выгрузка["status"] == 403, роль
        assert "31234567890123" not in список["body"] + выгрузка["body"]


@нужна_база
def test_список_поиск_повторы_и_карточка(люди):
    sql("delete from ilmora_registrations")
    первая = _заявка(created_at="2026-09-01 10:00:00")
    _заявка(full_name="Каримов Анвар Олимович", created_at="2026-10-02 10:00:00")
    юрлицо = _заявка(
        person_type="legal",
        phone="+998901112233",
        full_name="Саидова Нодира Акмаловна",
        pinfl=None,
        tin="305123456",
        created_at="2026-10-03 10:00:00",
    )

    _, все, поиск, юр, повторы, карточка = django(
        люди["admin"],
        ("get", LIST, None),
        ("get", LIST + "?q=305123456", None),
        ("get", LIST + "?person_type__exact=legal", None),
        ("get", LIST + "?repeat=1", None),
        ("get", f"{LIST}{первая}/change/", None),
    )

    тело = все["body"]
    assert тело.index("Саидова") < тело.index("Каримов") < тело.index("Алиев"), "новые сверху"
    assert тело.count("повтор</span>") >= 2, "одинаковый телефон и ПИНФЛ помечены"
    assert "Саидова" in поиск["body"] and "Алиев" not in поиск["body"]
    assert "Саидова" in юр["body"] and "Каримов" not in юр["body"]
    assert "Алиев" in повторы["body"] and "Саидова" not in повторы["body"]
    assert карточка["status"] == 200
    for значение in ("31234567890123", "203.0.113.5", "Узбекский", "draft", "01.10.2026"):
        assert значение in карточка["body"], значение
    assert f"{LIST}{юрлицо}/delete/" not in карточка["body"]


@нужна_база
def test_выгрузка(люди):
    sql("delete from ilmora_registrations")
    _заявка()
    sql("delete from admin_actions")

    _, ответ = django(люди["admin"], ("get", LIST + "export/?format=csv", None))

    assert ответ["status"] == 200
    assert "ПИНФЛ" in ответ["body"] and "31234567890123" in ответ["body"]
    assert sql("select action, section from admin_actions") == [("exported", "ilmora")]
