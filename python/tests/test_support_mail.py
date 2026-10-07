"""
Письма в поддержку → обращения (savdex/support/mail.py).

- новое письмо — обращение «Почта», пользователь с этой почтой — сразу его;
- то же письмо второй раз не заводится;
- ответ поддержки уходит клиенту письмом «Re: … [№N]» с цепочкой
  (In-Reply-To), под ответом — «ушло на почту»;
- ответ клиента на него — в то же обращение, без цитаты, ждавшее клиента
  обращение снова открыто;
- чужое письмо с номером в теме заводит своё обращение;
- автоответ пропускается, отказ доставки — внутренняя заметка;
- вложение — в закрытое хранилище, скачивается из админки, мелкая
  картинка подписи пропускается;
- ящик по IMAP: прочитанное помечается, сбой разбора — флажком.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL) — кроме проверок разбора.
"""

from __future__ import annotations

import re
import subprocess
import sys
from email import message_from_string, policy
from email.message import EmailMessage
from email.utils import make_msgid
from pathlib import Path

import pytest

from savdex.support import mail

from .pg_admin import PYTHON, ОКРУЖЕНИЕ, django, sql, журнал, нужна_база, свежая_база, сотрудник

PDF = b"%PDF-1.4\n" + b"0" * 20_000
LOGO = b"\x89PNG\r\n\x1a\n" + b"0" * 500


def _письмо(
    *,
    кому: str = "support@savdex.uz",
    от: str = "Азиз Каримов <aziz@mebel.uz>",
    тема: str = "Не могу оплатить тариф",
    текст: str = "Здравствуйте! Оплата через Click не проходит.",
    html: str | None = None,
    id: str | None = None,
    в_ответ: str | None = None,
    вложения: tuple[tuple[str, str, bytes], ...] = (),
    заголовки: dict[str, str] | None = None,
) -> tuple[bytes, str]:
    message = EmailMessage()
    message["From"] = от
    message["To"] = кому
    message["Subject"] = тема
    message_id = id or make_msgid(domain="mebel.uz")
    message["Message-ID"] = message_id

    if в_ответ:
        message["In-Reply-To"] = в_ответ
        message["References"] = в_ответ

    for name, value in (заголовки or {}).items():
        message[name] = value

    message.set_content(текст)

    if html:
        message.add_alternative(html, subtype="html")

    for name, kind, content in вложения:
        main, sub = kind.split("/")
        message.add_attachment(content, maintype=main, subtype=sub, filename=name)

    return message.as_bytes(), message_id


# ── Разбор ──────────────────────────────────────────────────────────


def test_разбор_письма():
    raw, message_id = _письмо(
        тема="=?utf-8?b?0J3QtSDQvNC+0LPRgyDQvtC/0LvQsNGC0LjRgtGM?=",
        вложения=(("счёт.pdf", "application/pdf", PDF), ("logo.png", "image/png", LOGO)),
    )
    letter = mail.parse(raw)

    assert letter.message_id == message_id
    assert (letter.from_name, letter.from_email) == ("Азиз Каримов", "aziz@mebel.uz")
    assert letter.subject == "Не могу оплатить"
    assert letter.text == "Здравствуйте! Оплата через Click не проходит."
    assert [a.name for a in letter.attachments] == ["счёт.pdf"], "логотип подписи пропущен"
    assert not letter.automatic and not letter.bounce


def test_только_html():
    raw, _ = _письмо(
        текст="",
        html="<html><head><style>p{color:red}</style></head><body><p>Привет,</p>"
        "<p>нужен <b>счёт</b>&nbsp;для&nbsp;бухгалтерии</p></body></html>",
    )
    # Письмо без текстовой части — только HTML
    message = EmailMessage()
    message["From"] = "a@b.uz"
    message["Subject"] = "HTML"
    message.set_content(
        "<p>Привет,</p><p>нужен <b>счёт</b>&nbsp;для бухгалтерии</p>", subtype="html"
    )

    assert mail.parse(message.as_bytes()).text == "Привет,\n\nнужен счёт для бухгалтерии"
    del raw


def test_цитата_отрезается():
    assert (
        mail.strip_quote(
            "Спасибо, получилось!\n\nOn Tue, 6 Oct 2026 at 10:00, SavdEx <support@savdex.uz> "
            "wrote:\n> Попробуйте ещё раз"
        )
        == "Спасибо, получилось!"
    )
    assert (
        mail.strip_quote("Да, верно\n\n6 окт. 2026 г., в 10:00, SavdEx написал:\n> текст")
        == "Да, верно"
    )
    assert mail.strip_quote("Ок\n\nFrom: SavdEx\nSent: Tuesday") == "Ок"
    assert mail.strip_quote("> только цитата") == "> только цитата", "пусто — весь текст"


def test_автоответ_и_отказ():
    auto, _ = _письмо(заголовки={"Auto-Submitted": "auto-replied"})
    daemon, _ = _письмо(от="Mail Delivery System <MAILER-DAEMON@mx.mebel.uz>")

    assert mail.parse(auto).automatic
    assert mail.parse(daemon).bounce


# ── С базой ─────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    return {role: сотрудник(role) for role in ("superadmin", "support")}


@pytest.fixture
def чисто(люди, tmp_path) -> Path:
    sql("delete from support_messages")
    sql("delete from support_tickets")
    sql("delete from admin_actions")
    sql("delete from users where email = 'aziz@mebel.uz'")

    return tmp_path


def _загрузить(root: Path, *письма: bytes) -> list[str]:
    files = []

    for number, raw in enumerate(письма):
        path = root / f"{number}.eml"
        path.write_bytes(raw)
        files.append(str(path))

    вывод = subprocess.run(
        [sys.executable, "manage.py", "support_mail", "--eml", *files],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "DJANGO_SETTINGS_MODULE": "savdex.settings", "LARAVEL_ROOT": str(root)},
        capture_output=True,
        text=True,
    )
    assert вывод.returncode == 0, вывод.stderr[-3000:]

    return вывод.stdout.splitlines()


def _ответить(uid: int, ticket: int, root: Path, text: str) -> dict:
    почта = root / "mail.log"
    _, ответ = django(
        uid,
        ("post", f"/py/admin/support/ticket/{ticket}/reply/", {"body": text}),
        env={"MAIL_MAILER": "log", "MAIL_LOG_PATH": str(почта), "LARAVEL_ROOT": str(root)},
    )
    assert ответ["status"] == 302, ответ["body"][:2000]

    return {"log": почта.read_text(encoding="utf-8") if почта.exists() else ""}


@нужна_база
def test_новое_обращение_и_дубль(люди, чисто):
    [(company,)] = sql(
        "insert into companies (name, slug, status, created_at, updated_at) values "
        "('Мебель Плюс', 'mebel-plus', 'active', now(), now()) returning id"
    )
    [(user,)] = sql(
        "insert into users (name, email, password, status, company_id, created_at, updated_at) "
        "values ('Азиз', 'aziz@mebel.uz', 'x', 'active', %s, now(), now()) returning id",
        [company],
    )
    raw, message_id = _письмо(от="Азиз Каримов <Aziz@Mebel.uz>")

    итог = _загрузить(чисто, raw, raw)

    assert "created" in итог[0] and "уже загружено" in итог[1]
    [(pk, subject, user_id, company_id, name, email, channel, status)] = sql(
        "select id, subject, user_id, company_id, author_name, author_email, channel, status "
        "from support_tickets"
    )
    assert (subject, user_id, company_id, name, email, channel, status) == (
        "Не могу оплатить тариф",
        user,
        company,
        "Азиз Каримов",
        "aziz@mebel.uz",
        "email",
        "open",
    )
    assert sql("select body, from_staff, author_id, email_message_id from support_messages") == [
        ("Здравствуйте! Оплата через Click не проходит.", False, user, message_id)
    ]
    assert журнал("created")["section"] == "support"
    del pk


@нужна_база
def test_ответ_письмом_и_ответ_клиента(люди, чисто):
    raw, client_id = _письмо()
    _загрузить(чисто, raw)
    [(ticket,)] = sql("select id from support_tickets")

    письма = _ответить(люди["support"], ticket, чисто, "Попробуйте ещё раз через Payme.")["log"]
    parsed = message_from_string(письма, policy=policy.default)

    assert "aziz@mebel.uz" in parsed["To"]
    assert str(parsed["Subject"]).strip() == f"Re: Не могу оплатить тариф [№{ticket}]"
    assert parsed["In-Reply-To"] == client_id
    our_id = str(parsed["Message-ID"])
    assert re.fullmatch(rf"<support-{ticket}-\d+\.[0-9a-f]+@savdex\.uz>", our_id)
    assert "support@savdex.uz" in str(parsed["Reply-To"])
    assert sql("select status from support_tickets") == [("waiting",)]
    assert sql(
        "select emailed_at is not null, email_message_id from support_messages where from_staff"
    ) == [(True, our_id)]

    # Клиент отвечает на наше письмо — то же обращение, без цитаты
    ответ, _ = _письмо(
        тема=f"Re: Не могу оплатить тариф [№{ticket}]",
        текст="Через Payme получилось, спасибо!\n\nOn Tue, SavdEx wrote:\n> Попробуйте ещё",
        в_ответ=our_id,
    )
    итог = _загрузить(чисто, ответ)

    assert f"appended {ticket}" in итог[0]
    assert sql("select count(*) from support_tickets") == [(1,)]
    assert sql("select status from support_tickets") == [("open",)], "ждавшее клиента — открыто"
    assert sql("select body from support_messages order by id desc limit 1") == [
        ("Через Payme получилось, спасибо!",)
    ]


@нужна_база
def test_чужое_письмо_с_номером(люди, чисто):
    raw, _ = _письмо()
    _загрузить(чисто, raw)
    [(ticket,)] = sql("select id from support_tickets")
    чужое, _ = _письмо(от="other@spam.uz", тема=f"Re: что-то [№{ticket}]")

    итог = _загрузить(чисто, чужое)

    assert "created" in итог[0]
    assert sql("select author_email, subject from support_tickets order by id") == [
        ("aziz@mebel.uz", "Не могу оплатить тариф"),
        ("other@spam.uz", "Re: что-то"),
    ]


@нужна_база
def test_автоответ_и_отказ_доставки(люди, чисто):
    raw, _ = _письмо()
    _загрузить(чисто, raw)
    [(ticket,)] = sql("select id from support_tickets")
    our = f"<support-{ticket}-1.abcdef@savdex.uz>"
    авто, _ = _письмо(тема="Я в отпуске", заголовки={"Auto-Submitted": "auto-replied"})
    отказ, _ = _письмо(
        от="Mail Delivery System <MAILER-DAEMON@mx.mebel.uz>",
        тема="Undelivered Mail Returned to Sender",
        текст=f"The mail system: <aziz@mebel.uz>: user unknown\n\nMessage-ID: {our}",
    )
    себе, _ = _письмо(от="SavdEx <support@savdex.uz>")

    итог = _загрузить(чисто, авто, отказ, себе)

    assert "skipped" in итог[0] and "автоответ" in итог[0]
    assert f"appended {ticket}" in итог[1]
    assert "письмо самим себе" in итог[2]
    assert sql("select count(*) from support_tickets") == [(1,)]
    [(body, internal)] = sql(
        "select body, is_internal from support_messages where from_staff order by id"
    )
    assert internal and body.startswith("Письмо клиенту не доставлено")


@нужна_база
def test_вложения(люди, чисто):
    raw, _ = _письмо(
        вложения=(("счёт.pdf", "application/pdf", PDF), ("logo.png", "image/png", LOGO))
    )
    _загрузить(чисто, raw)
    [(ticket,)] = sql("select id from support_tickets")
    [(message, files)] = sql("select id, attachments::text from support_messages")

    assert '"name": "счёт.pdf"' in files
    path = re.search(r'"path": "([^"]+)"', files)
    assert path and (чисто / "storage/app/private" / path.group(1)).read_bytes() == PDF

    _, страница, файл = django(
        люди["support"],
        ("get", f"/py/admin/support/ticket/{ticket}/change/", None),
        ("get", f"/py/admin/support/ticket/{ticket}/file/{message}/0/", None),
        env={"LARAVEL_ROOT": str(чисто)},
    )

    assert "счёт.pdf" in страница["body"] and "Пришло письмом" in страница["body"]
    assert файл["status"] == 200 and файл["body"].startswith("%PDF")


@нужна_база
def test_ящик_по_imap(люди, чисто):
    """Ящик: новое письмо — обращение и «прочитано»; битое — флажок."""
    raw, _ = _письмо()
    script = f"""
import django; django.setup()
from savdex.support import mail

class Box:
    stored = []
    def __init__(self, host, port, timeout): pass
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def login(self, u, p): pass
    def select(self, folder): return ("OK", [b"2"])
    def uid(self, command, *args):
        if command == "search":
            return ("OK", [b"1 2"])
        if command == "fetch":
            body = {raw!r} if args[0] == "1" else None
            return ("OK", [(b"1 (BODY[] {{1}}", body)] if body else [])
        if command == "store":
            Box.stored.append((args[0], args[2]))
            return ("OK", [])

mail.imaplib.IMAP4_SSL = Box
mail.os.environ.update(SUPPORT_IMAP_HOST="imap.test", SUPPORT_IMAP_USERNAME="s@savdex.uz",
                       SUPPORT_IMAP_PASSWORD="x")
print(mail.run(), Box.stored)
"""
    вывод = subprocess.run(
        [sys.executable, "-c", script],
        cwd=PYTHON,
        env={
            **ОКРУЖЕНИЕ,
            "DJANGO_SETTINGS_MODULE": "savdex.settings",
            "PYTHONPATH": str(PYTHON),
            "LARAVEL_ROOT": str(чисто),
        },
        capture_output=True,
        text=True,
    )

    assert вывод.returncode == 0, вывод.stderr[-3000:]
    assert "новых 1" in вывод.stdout
    assert "('1', '(\\\\Seen)')" in вывод.stdout
    assert sql("select count(*) from support_tickets") == [(1,)]


@нужна_база
def test_без_почты_клиента(люди, чисто):
    [(ticket,)] = sql(
        "insert into support_tickets (subject, status, channel, priority, created_at, updated_at) "
        "values ('Звонок', 'open', 'phone', 'normal', now(), now()) returning id"
    )
    _, страница = django(
        люди["support"], ("get", f"/py/admin/support/ticket/{ticket}/change/", None)
    )

    assert "нет почты клиента" in страница["body"]

    письма = _ответить(люди["support"], ticket, чисто, "Перезвоним завтра")["log"]

    assert письма == "", "письма нет — некому"
    assert sql("select status from support_tickets") == [("waiting",)]
