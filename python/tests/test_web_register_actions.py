"""
Регистрация на Django неотличима от Laravel: подготовка ввода (почта
строчными, имя без пробелов), проверка (строгая почта, занятая — своя
ошибка, телефон, правило пароля площадки, согласие с условиями) и
подсказки после неё, новая учётка, письмо с кодом и подписанной ссылкой
(оформление — как у Laravel), код в кэше, вход и переход к данным
компании. Письма обеих сторон — в журнале (MAIL_MAILER=log): Laravel —
storage/logs/laravel.log, Django — MAIL_LOG_PATH.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import email
import hashlib
import json
import re
import shutil
from collections.abc import Iterator
from email.message import Message
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

import pytest

from savdex import laravel_session

from .pg_admin import APP_KEY, KEY, КОРЕНЬ, sql, нужна_база, свежая_база
from .test_web_forms import SID, ТОКЕН, inertia
from .test_web_session import СЕССИЯ, завести, кука, строка
from .web_site import laravel, из_django, из_laravel

pytestmark = нужна_база

ЖУРНАЛ_LARAVEL = Path(КОРЕНЬ) / "storage/logs/laravel.log"
ЖУРНАЛ_DJANGO = Path(КОРЕНЬ) / "storage/logs/python-mail-test.log"
КЭШ = Path(КОРЕНЬ) / "storage/framework/cache/data"
ОКРУЖЕНИЕ_ПОЧТЫ = {"MAIL_MAILER": "log", "CACHE_STORE": "file", "LOG_CHANNEL": "single"}


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    with laravel(**ОКРУЖЕНИЕ_ПОЧТЫ) as root:
        yield root


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


def регистрация(сайт: str, body: dict[str, Any], *, занята: bool = False) -> dict[str, Any]:
    стороны = {}

    for имя, сторона in (("django", из_django), ("laravel", из_laravel)):
        sql("delete from users where email like '%%@reg.savdex.uz' or email = 'taken@savdex.uz'")
        shutil.rmtree(КЭШ, ignore_errors=True)
        ЖУРНАЛ_LARAVEL.write_text("")
        ЖУРНАЛ_DJANGO.write_text("")

        if занята:
            sql(
                "insert into users (name, email, password, status, deleted_at, created_at, "
                "updated_at) values ('Был', 'taken@savdex.uz', 'x', 'active', now(), now(), now())"
            )

        завести(SID, {"_token": ТОКЕН})
        kwargs: dict[str, Any] = {
            "method": "POST",
            "body": json.dumps(body),
            "content_type": "application/json",
        }

        if сторона is из_django:
            kwargs["env"] = {**ОКРУЖЕНИЕ_ПОЧТЫ, "MAIL_LOG_PATH": str(ЖУРНАЛ_DJANGO)}

        ответ = сторона(
            сайт,
            "/register",
            {СЕССИЯ: кука(СЕССИЯ, SID)},
            {**inertia(), "Referer": сайт + "/register", "User-Agent": "savdex-parity"},
            **kwargs,
        )
        кука_сессии = ответ["cookies"].get(СЕССИЯ)
        sid = (
            laravel_session.cookie_value(СЕССИЯ, unquote(кука_сессии["value"]), [KEY])
            if кука_сессии
            else None
        )
        сессия = строка(sid) if sid else None
        журнал = (ЖУРНАЛ_DJANGO if сторона is из_django else ЖУРНАЛ_LARAVEL).read_text()
        письма = [_разбор(п) for п in _письма(журнал)]
        учётки = sql(
            "select id, name, email, phone, password like '$2y$12$%%', locale, account_type, "
            "company_role, email_verified_at is not null, status from users "
            "where email like '%%@reg.savdex.uz' order by id"
        )

        for письмо in письма:
            _проверить_письмо(письмо, учётки[0][0], учётки[0][2])

        стороны[имя] = {
            "status": ответ["status"],
            "location": ответ["headers"].get("location"),
            "session": None
            if сессия is None
            else {
                "payload": re.sub(r'("login_web_\w+":)\d+', r"\1<номер>", сессия["payload"]),
                "user_id": сессия["user_id"] is not None,
            },
            "users": [r[1:] for r in учётки],
            "mail": [{k: _без_изменчивого(v, сайт) for k, v in п.items()} for п in письма],
        }

    import os

    if os.environ.get("SAVDEX_DUMP"):
        for имя, данные in стороны.items():
            Path(os.environ["SAVDEX_DUMP"] + f"-{имя}.json").write_text(
                json.dumps(данные, ensure_ascii=False, indent=1, default=str)
            )

    assert стороны["django"] == стороны["laravel"], json.dumps(
        стороны, ensure_ascii=False, default=str
    )[:6000]

    return стороны["django"]


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
    "body",
    [
        ВЕРНО,
        {**ВЕРНО, "account_type": None, "locale": None},
        {**ВЕРНО, "password": "short1", "password_confirmation": "other"},
        {**ВЕРНО, "password": "onlyletterslong", "password_confirmation": "onlyletterslong"},
        {**ВЕРНО, "password": "1234567890123", "password_confirmation": "1234567890123"},
        {**ВЕРНО, "email": "aziz.reg.savdex.uz"},
        {**ВЕРНО, "email": "aziz@reg"},
        {**ВЕРНО, "email": "aziz(x)@reg.savdex.uz"},
        {**ВЕРНО, "phone": "12", "terms": False, "account_type": "robot"},
        {**ВЕРНО, "name": " ", "locale": "fr"},
        {},
    ],
)
def test_регистрация(сайт, body):
    итог = регистрация(сайт, body)

    if body is ВЕРНО:
        assert итог["location"].endswith("/onboarding/company") and len(итог["mail"]) == 1


def test_почта_занята(сайт):
    регистрация(сайт, {**ВЕРНО, "email": "taken@savdex.uz"}, занята=True)
