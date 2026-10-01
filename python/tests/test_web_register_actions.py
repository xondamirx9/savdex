"""
Регистрация на Django: третий шаг, анкета, с почтой,
подтверждённой кодом на первых двух (register.verified_email в сессии; без
неё — назад к первому шагу). Подготовка ввода (имя без пробелов), проверка
(строгая почта, занятая — своя ошибка, телефон, правило пароля площадки,
согласие с условиями) и подсказки после неё, новая учётка сразу с
подтверждённой почтой — без второго письма, вход и переход к данным
компании или в кабинет. Письма — в журнале (MAIL_MAILER=log, MAIL_LOG_PATH).

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import email
import hashlib
import json
import re
from collections.abc import Iterator
from email.message import Message
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import pytest

from savdex import laravel_session

from .factories import категория, компания
from .pg_admin import APP_KEY, KEY, КОРЕНЬ, sql, нужна_база, свежая_база
from .test_web_forms import SID, ТОКЕН, inertia
from .test_web_session import СЕССИЯ, завести, кука, строка
from .web_site import адрес, открыть

pytestmark = нужна_база

ЖУРНАЛ_LARAVEL = Path(КОРЕНЬ) / "storage/logs/laravel.log"
ЖУРНАЛ_DJANGO = Path(КОРЕНЬ) / "storage/logs/python-mail-test.log"
КЭШ = Path(КОРЕНЬ) / "storage/framework/cache/data"
ОКРУЖЕНИЕ_ПОЧТЫ = {"MAIL_MAILER": "log", "CACHE_STORE": "file", "LOG_CHANNEL": "single"}

#: Свой журнал писем и свой адрес посетителя: storage/ и файловый кэш
#: (счётчик регистраций с адреса) — общие с другими проверками
_ЖУРНАЛ = Path(КОРЕНЬ) / "storage/logs/python-mail-test-register.log"
IP = "198.51.100.48"


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    cement = категория(slug="cement", parent_id=None)
    категория(slug="metal", parent_id=None)
    категория(slug="child", parent_id=cement)
    компания(slug="taken", tin="305123456")

    try:
        with адрес() as root:
            yield root
    finally:
        _ЖУРНАЛ.unlink(missing_ok=True)


def _счётчик_с_нуля() -> None:
    """
    Счётчики с адреса IP — с нуля: созданные аккаунты (register:<IP>) и
    частота формы (throttle:20,10,register — «register» + sha1(«|IP»)).
    """
    from savdex import laravel_cache

    частота = "register" + hashlib.sha1(f"|{IP}".encode()).hexdigest()

    for ключ in (f"register:{IP}", частота):
        for имя in (ключ, ключ + ":timer"):
            laravel_cache.file_path(имя).unlink(missing_ok=True)


def _письма(текст: str) -> list[Message]:
    """Письма из журнала: MIME после «local.DEBUG:» (Laravel) или подряд (Django)."""
    части = re.split(r"^\[\d{4}-\d\d-\d\d [^\]]*\] \w+\.DEBUG: ", текст, flags=re.M)

    return [email.message_from_string(ч.strip()) for ч in части if "Subject:" in ч]


def _разбор(письмо: Message) -> dict[str, Any]:
    тела = {}

    for часть in письмо.walk():
        if часть.get_content_type() in ("text/plain", "text/html"):
            # Журнал Laravel уже раскодировал quoted-printable — тело как есть
            тела[часть.get_content_type()] = str(часть.get_payload(decode=False))

    return {
        "subject": str(email.header.make_header(email.header.decode_header(письмо["Subject"]))),
        "from": str(email.header.make_header(email.header.decode_header(письмо["From"]))),
        "to": письмо["To"],
        "text": тела.get("text/plain", "").replace("\r\n", "\n").strip(),
        "html": тела.get("text/html", "").replace("\r\n", "\n").strip(),
    }


def _без_изменчивого(текст: str, root: str) -> str:
    текст = re.sub(r"\b\d{6}\b", "<код>", текст)
    текст = re.sub(r"expires=\d+", "expires=<срок>", текст)
    текст = re.sub(r"signature=[0-9a-f]{64}", "signature=<подпись>", текст)
    текст = re.sub(r"/verify-email/\d+/", "/verify-email/<номер>/", текст)

    return текст.replace(root, "<сайт>")


def _проверить_письмо(письмо: dict[str, Any], uid: int, адрес: str) -> None:
    """Код из письма сходится с хешем в кэше, подпись ссылки верна."""
    import bcrypt

    from savdex.web.currency import unserialize

    код = re.search(r"# (\d{6})", письмо["text"]).group(1)  # type: ignore[union-attr]
    файл = hashlib.sha1(f"email_verification_code.{uid}".encode()).hexdigest()
    сырое = (КЭШ / файл[:2] / файл[2:4] / файл).read_bytes()
    запись = unserialize(сырое[10:])
    assert isinstance(запись, dict) and запись["attempts"] == 0
    assert bcrypt.checkpw(код.encode(), ("$2b$" + запись["hash"][4:]).encode())

    ссылка = re.search(r"Или подтвердите одним нажатием: (\S+)", письмо["text"]).group(1)  # type: ignore[union-attr]
    части = urlsplit(ссылка)
    assert части.path == f"/verify-email/{uid}/{hashlib.sha1(адрес.encode()).hexdigest()}"
    без_подписи = (
        f"{части.scheme}://{части.netloc}{части.path}?" + части.query.split("&signature=")[0]
    )
    import hmac

    ожидание = hmac.new(APP_KEY.encode(), без_подписи.encode(), hashlib.sha256).hexdigest()
    assert части.query.endswith("signature=" + ожидание)


def регистрация(
    сайт: str,
    body: dict[str, Any],
    *,
    занята: bool = False,
    лимит: bool = False,
    отключена: bool = True,
    подтверждена: bool = True,
) -> dict[str, Any]:
    sql("delete from users where email like '%%@reg.savdex.uz' or email = 'taken@savdex.uz'")
    sql("delete from companies where slug <> 'taken'")
    sql("select setval('companies_id_seq', (select max(id) from companies) + 1, false)")
    _счётчик_с_нуля()
    _ЖУРНАЛ.parent.mkdir(parents=True, exist_ok=True)
    _ЖУРНАЛ.write_text("")

    if лимит:
        # Пять созданных аккаунтов с этого адреса — полчаса назад
        import os
        import time

        from savdex import laravel_cache

        os.environ["CACHE_STORE"] = "file"
        laravel_cache.put(f"register:{IP}", 5, 3600)
        laravel_cache.put(f"register:{IP}:timer", int(time.time()) + 1800, 3600)

    if занята:
        sql(
            "insert into users (name, email, password, status, deleted_at, created_at, "
            "updated_at) values ('Был', 'taken@savdex.uz', 'x', 'active', %s, now(), now())",
            ["2026-01-01 00:00:00" if отключена else None],
        )

    # Шаги 1–2 пройдены: почта из формы — та, что подтверждена кодом
    данные: dict[str, Any] = {"_token": ТОКЕН}

    if подтверждена and isinstance(body.get("email"), str):
        адрес_ = body["email"].strip().lower()
        данные["register"] = {"email": адрес_, "verified_email": адрес_}

    завести(SID, данные)

    try:
        ответ = открыть(
            сайт,
            "/register",
            {СЕССИЯ: кука(СЕССИЯ, SID)},
            {
                **inertia(),
                "Referer": сайт + "/register",
                "User-Agent": "savdex-parity",
                "X-Forwarded-For": IP,
            },
            {**ОКРУЖЕНИЕ_ПОЧТЫ, "MAIL_LOG_PATH": str(_ЖУРНАЛ)},
            method="POST",
            body=json.dumps(body),
            content_type="application/json",
        )
    finally:
        _счётчик_с_нуля()

    кука_сессии = ответ["cookies"].get(СЕССИЯ)
    sid = (
        laravel_session.cookie_value(СЕССИЯ, unquote(кука_сессии["value"]), [KEY])
        if кука_сессии
        else None
    )
    сессия = строка(sid) if sid else None
    письма = [_разбор(п) for п in _письма(_ЖУРНАЛ.read_text())]
    учётки = sql(
        "select id, name, email, phone, password like '$2y$12$%%', locale, account_type, "
        "company_role, email_verified_at is not null, status from users "
        "where (email like '%%@reg.savdex.uz' or email = 'taken@savdex.uz') "
        "and deleted_at is null order by id"
    )

    for письмо in письма:
        _проверить_письмо(письмо, учётки[0][0], учётки[0][2])

    return {
        "status": ответ["status"],
        "location": ответ["headers"].get("location"),
        "session": None
        if сессия is None
        else {
            "payload": re.sub(r'("login_web_\w+":)\d+', r"\1<номер>", сессия["payload"]),
            "user_id": сессия["user_id"] is not None,
        },
        "users": [r[1:] for r in учётки],
        "companies": sql(
            "select name, slug, legal_form, tin, primary_role, status, is_it_provider, "
            "it_specializations::text, search_text, (select array_agg(c.slug order by c.slug) "
            "from company_category cc join categories c on c.id = cc.category_id "
            "where cc.company_id = companies.id)::text from companies "
            "where slug <> 'taken' order by id"
        ),
        "mail": [{k: _без_изменчивого(v, сайт) for k, v in п.items()} for п in письма],
    }


def _сессия(итог: dict[str, Any]) -> dict[str, Any]:
    """Строка сессии после ответа (номер вошедшего — 0)."""
    return dict(json.loads(итог["session"]["payload"].replace("<номер>", "0")))


def _ошибки(итог: dict[str, Any]) -> dict[str, list[str]]:
    return dict(_сессия(итог)["errors"]["default"]["messages"])


СОЗДАНА = "Компания создана. Осталось подтвердить почту — и можно публиковать объявления."

ВЕРНО = {
    "name": "  Азиз Каримов ",
    "email": " Aziz@Reg.Savdex.UZ ",
    "phone": "+998 90 123-45-67",
    "password": "Cement2027x",
    "password_confirmation": "Cement2027x",
    "terms": True,
    "account_type": "individual",
    "locale": "uz",
}


@pytest.mark.parametrize(
    ("body", "ошибки"),
    [
        (ВЕРНО, None),
        # Без вида — юрлицо: нужны название и разделы
        ({**ВЕРНО, "account_type": None, "locale": None}, {"company_name", "categories"}),
        (
            {**ВЕРНО, "password": "short1", "password_confirmation": "other"},
            {"password", "password_confirmation"},
        ),
        # Правило пароля площадки: и буквы, и цифры
        (
            {**ВЕРНО, "password": "onlyletterslong", "password_confirmation": "onlyletterslong"},
            {"password": ["Добавьте в пароль хотя бы одну цифру"]},
        ),
        (
            {**ВЕРНО, "password": "1234567890123", "password_confirmation": "1234567890123"},
            {"password": ["Добавьте в пароль хотя бы одну букву"]},
        ),
        # Строгая почта — свои подсказки
        (
            {**ВЕРНО, "email": "aziz.reg.savdex.uz"},
            {"email": ["В адресе не хватает знака @. Например: rustam@company.uz"]},
        ),
        (
            {**ВЕРНО, "email": "aziz@reg"},
            {"email": ["Похоже, адрес неполный. Нужен формат name@company.uz"]},
        ),
        (
            {**ВЕРНО, "email": "aziz(x)@reg.savdex.uz"},
            {"email": ["Проверьте адрес: нужен формат name@company.uz"]},
        ),
        (
            {**ВЕРНО, "phone": "12", "terms": False, "account_type": "robot"},
            {"phone", "terms", "account_type", "company_name", "categories"},
        ),
        # Имя из одних пробелов — пустое
        ({**ВЕРНО, "name": " ", "locale": "fr"}, {"name", "locale"}),
        ({}, "к первому шагу"),
    ],
)
def test_регистрация(сайт, body, ошибки):
    итог = регистрация(сайт, body)

    assert итог["status"] == 302

    if ошибки is None:
        # Почта подтверждена до анкеты: сразу в кабинет, второго письма нет
        assert итог["location"].endswith("/cabinet") and итог["mail"] == []
        assert итог["users"] == [
            (
                "Азиз Каримов",
                "aziz@reg.savdex.uz",
                "+998 90 123-45-67",
                True,
                "uz",
                "individual",
                "owner",
                True,
                "active",
            )
        ]
        assert итог["companies"][0][:3] == ("Азиз Каримов", "aziz-karimov", "individual")
        # Вошёл; шаги регистрации из сессии убраны
        assert итог["session"]["user_id"] is True
        assert _сессия(итог)["success"] == СОЗДАНА
        assert _сессия(итог)["register"] == []
    elif ошибки == "к первому шагу":
        # Без почты нет и подтверждения — к первому шагу
        assert итог["location"].endswith("/register") and итог["users"] == []
        assert "errors" not in _сессия(итог)
    else:
        assert итог["location"].endswith("/register")
        assert итог["users"] == [] and итог["companies"] == []
        найдено = _ошибки(итог)

        if isinstance(ошибки, dict):
            assert найдено == ошибки
        else:
            assert set(найдено) == ошибки

        # Ввод — обратно в форму, но без паролей; имя — без пробелов по краям
        ввод = _сессия(итог)["_old_input"]
        assert "password" not in ввод and "password_confirmation" not in ввод
        assert ввод["name"] == body["name"].strip()


def _раздел(slug: str) -> int:
    return int(sql("select id from categories where slug = %s", [slug])[0][0])


ЮРЛИЦО = {
    **ВЕРНО,
    "account_type": "legal",
    "company_name": "  ООО «Цемент Плюс» ",
    "tin": "302 345-678",
    "categories": "cement,metal",
}


@pytest.mark.parametrize(
    ("правка", "итог_"),
    [
        ({}, "{cement,metal}"),
        ({"tin": None, "company_name": ""}, {"company_name": ["Укажите название компании"]}),
        (
            {"tin": "305123456"},
            {"tin": ["Компания с таким ИНН уже зарегистрирована на площадке"]},
        ),
        ({"tin": "30234567"}, {"tin": ["ИНН (СТИР) в Узбекистане — ровно 9 цифр."]}),
        ({"categories": []}, {"categories": ["Выберите хотя бы одну категорию"]}),
        # Повтор раздела — один раз
        ({"categories": "cement,cement"}, "{cement}"),
        # Подраздел не годится — только разделы верхнего уровня
        ({"categories": "child"}, {"categories.0"}),
        ({"categories": ["x", 99999]}, {"categories.0", "categories.1"}),
        ({"account_type": "robot"}, {"account_type"}),
    ],
)
def test_регистрация_юрлица(сайт, правка, итог_):
    body = {**ЮРЛИЦО, **правка}

    if isinstance(body["categories"], str):
        body["categories"] = [_раздел(s) for s in body["categories"].split(",")]

    итог = регистрация(сайт, body)

    assert итог["status"] == 302

    if isinstance(итог_, str):
        # Юрлицо — дальше к данным компании; ИНН без пробелов и дефисов
        assert итог["location"].endswith("/onboarding/company")
        [компания_] = итог["companies"]
        assert компания_[:4] == ("ООО «Цемент Плюс»", "ooo-tsement-plius", "legal", "302345678")
        assert компания_[8] == "ооо «цемент плюс» ooo «sement plyus»"
        assert компания_[9] == итог_
        assert итог["users"][0][5:7] == ("legal", "owner")
    else:
        assert итог["location"].endswith("/register")
        assert итог["users"] == [] and итог["companies"] == []
        найдено = _ошибки(итог)
        assert (найдено if isinstance(итог_, dict) else set(найдено)) == итог_


@pytest.mark.parametrize(
    ("правка", "итог_"),
    [
        # Фрилансер из IT — сразу с IT-направлениями; ПИНФЛ — без пробелов
        (
            {"account_type": "freelancer", "pinfl": "3120 5967 8901 23", "service_section": "it"},
            ("freelancer", "31205967890123", True),
        ),
        (
            {"account_type": "freelancer", "pinfl": None, "service_section": "cooking"},
            {
                "pinfl": ["Укажите ПИНФЛ — 14 цифр"],
                "service_section": ["Выберите направление услуг"],
            },
        ),
        (
            {"account_type": "freelancer", "pinfl": "11111111111111", "service_section": "hr_services"},
            {"pinfl": ["Указан недействительный ПИНФЛ"]},
        ),
        ({"account_type": "individual", "pinfl": "123"}, {"pinfl": ["ПИНФЛ — ровно 14 цифр"]}),
        # Название компании у физлица не нужно — название из имени
        (
            {"account_type": "individual", "pinfl": "31205967890123", "company_name": "лишнее"},
            ("individual", "31205967890123", False),
        ),
    ],
)
def test_регистрация_человека(сайт, правка, итог_):
    итог = регистрация(сайт, {**ВЕРНО, **правка})

    assert итог["status"] == 302

    if isinstance(итог_, tuple):
        assert итог["location"].endswith("/cabinet")
        [компания_] = итог["companies"]
        assert компания_[:2] == ("Азиз Каримов", "aziz-karimov")
        assert (компания_[2], компания_[3], компания_[6]) == итог_
        assert (компания_[7] is not None) is итог_[2]
        assert итог["users"][0][5] == итог_[0]
    else:
        assert итог["location"].endswith("/register") and итог["users"] == []
        assert _ошибки(итог) == итог_


def test_лимит_регистраций(сайт):
    итог = регистрация(сайт, ВЕРНО, лимит=True)

    assert итог["users"] == [] and итог["location"].endswith("/register")
    assert _сессия(итог)["error"].startswith(
        "С этого адреса сети за последний час уже зарегистрировали несколько аккаунтов"
    )


def test_почта_отключённого_свободна(сайт):
    """Отключённый (удалённый) аккаунт адрес не держит — регистрация проходит."""
    итог = регистрация(сайт, {**ВЕРНО, "email": "taken@savdex.uz"}, занята=True)

    assert len(итог["users"]) == 1
    assert итог["users"][0][:2] == ("Азиз Каримов", "taken@savdex.uz")
    assert итог["location"].endswith("/cabinet")


def test_почта_занята(сайт):
    итог = регистрация(сайт, {**ВЕРНО, "email": "taken@savdex.uz"}, занята=True, отключена=False)

    assert len(итог["users"]) == 1 and итог["location"].endswith("/register")
    assert итог["users"][0][0] == "Был"
    assert _ошибки(итог) == {
        "email": ["На этот адрес уже зарегистрирована компания. Войдите или восстановите пароль"]
    }


def test_без_подтверждённой_почты_анкета_не_принимается(сайт):
    """Почта в форме без кода на втором шаге — назад к первому шагу, аккаунта нет."""
    итог = регистрация(сайт, ВЕРНО, подтверждена=False)

    assert итог["location"].endswith("/register") and итог["users"] == []
    assert "errors" not in _сессия(итог)
