"""
Обращения по почте: письмо на ящик поддержки — обращение в админке, ответ
поддержки — письмо клиенту.

Входящие. Фоновый обработчик (manage.py notify, раз в минуту; вручную —
manage.py support_mail) читает непрочитанные письма ящика поддержки по
IMAP (SUPPORT_IMAP_HOST, _PORT, _USERNAME, _PASSWORD, _FOLDER) и по каждому:

- продолжение переписки — сообщением в её обращение. Узнаётся по ответу
  на наше письмо (In-Reply-To/References с нашим Message-ID), по ответу
  на прежнее письмо клиента или по номеру в теме «[№123]». Только если
  пишет тот же человек (почта обращения или его учётной записи): чужое
  письмо с подсмотренным номером заводит своё обращение. Закрытое или
  ждавшее клиента обращение снова открыто; цитата прошлой переписки
  отрезается;
- иначе — новое обращение «Почта»: тема, имя и почта отправителя; есть
  на площадке пользователь с этой почтой — обращение сразу его и его
  компании;
- вложения — в закрытое хранилище (storage/app/private/support/…),
  скачиваются из админки;
- одно письмо дважды не заводится (Message-ID в support_messages);
- автоответы, рассылки, письма самому себе и с адресов no-reply
  пропускаются, как и письма отправителей из спам-фильтра
  (savdex/support/spam.py); отказ доставки нашего ответа («адрес не
  существует») — внутренней заметкой в его обращение.

Письмо помечается прочитанным, когда записано; письмо, на котором разбор
упал, — ещё и флажком: его видно в ящике.

Ответ (reply). Ответ поддержки, не заметка, уходит клиенту письмом:
«Re: тема [№123]», наш Message-ID и In-Reply-To на последнее письмо
клиента — почтовая программа клиента держит всё одной цепочкой, а его
ответ возвращается в обращение. Почтовик — SUPPORT_MAIL_* если задан,
иначе почта сайта (MAIL_*, Brevo): ответ на вопрос клиента — служебное
письмо. «От кого» и «Ответить» — адрес поддержки из настроек площадки
(support_email) или SUPPORT_MAIL_FROM_ADDRESS.
"""

from __future__ import annotations

import imaplib
import logging
import os
import re
import secrets
from dataclasses import dataclass, field
from email import message_from_bytes, policy
from email.message import EmailMessage
from email.utils import formataddr, getaddresses, parseaddr
from html.parser import HTMLParser
from pathlib import Path
from typing import Any, ClassVar

from django.db import connection, transaction
from django.utils import timezone

from savdex import audit
from savdex.catalog import now
from savdex.laravel_storage import private_root
from savdex.support import spam
from savdex.support.models import (
    STATUS_CLOSED,
    STATUS_OPEN,
    STATUS_WAITING,
    STATUS_WORKING,
    Message,
    Ticket,
)
from savdex.web import mail

log = logging.getLogger("savdex.support.mail")

TICKET_MODEL = "App\\Models\\Support\\Ticket"

#: Писем за проход
LIMIT = 20

#: Вложения: сколько на письмо, размер одного и всех вместе
MAX_FILES = 10
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_TOTAL_BYTES = 25 * 1024 * 1024

#: Картинки меньше этого — логотипы подписей и пиксели слежения
MIN_IMAGE_BYTES = 8 * 1024

#: Текст сообщения — не длиннее
MAX_BODY = 50_000

#: Номер обращения в теме письма: «[№123]» или «[#123]»
_TAG = re.compile(r"\[\s*(?:№|#)\s*(\d{1,18})\s*\]")

#: Наш Message-ID ответа: <support-обращение-сообщение.случайное@домен>
_OUR_ID = re.compile(r"<support-(\d{1,18})-(\d{1,18})\.[0-9a-f]+@[^>]+>")

#: Отправители отказов доставки
_DAEMONS = ("mailer-daemon", "postmaster")

#: Адреса, на которые не отвечают: no-reply, noreply, do-not-reply,
#: donotreply… — уведомления сервисов, а не вопросы клиентов
_NO_REPLY = re.compile(r"^(?:no|do[-_.]?not)[-_.]?reply(?:[-_.+\d].*)?$")


# ── Настройки ──────────────────────────────────────────────────────


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


@dataclass(frozen=True)
class Imap:
    host: str
    port: int
    username: str
    password: str
    folder: str


def imap() -> Imap | None:
    """Ящик поддержки по IMAP; не задан — входящие не читаются."""
    host, username, password = (
        _env("SUPPORT_IMAP_HOST"),
        _env("SUPPORT_IMAP_USERNAME"),
        _env("SUPPORT_IMAP_PASSWORD"),
    )

    if not (host and username and password):
        return None

    try:
        port = int(_env("SUPPORT_IMAP_PORT") or 993)
    except ValueError:
        port = 993

    return Imap(host, port, username, password, _env("SUPPORT_IMAP_FOLDER") or "INBOX")


def address() -> str:
    """Адрес поддержки: SUPPORT_MAIL_FROM_ADDRESS или «Почта поддержки» из настроек."""
    if configured := _env("SUPPORT_MAIL_FROM_ADDRESS"):
        return configured.lower()

    from savdex.web.shared import setting, settings_values

    return setting(settings_values(), "support_email", "support@savdex.uz").strip().lower()


def _prefix() -> str:
    """Почтовик ответа: свой (SUPPORT_MAIL_*), если задан, иначе почта сайта."""
    return "SUPPORT_MAIL" if _env("SUPPORT_MAIL_MAILER") else "MAIL"


def _ours() -> set[str]:
    """Свои адреса: письма с них — не клиенты (петля автоответов)."""
    own = {address(), _env("MAIL_FROM_ADDRESS").lower(), _env("SUPPORT_IMAP_USERNAME").lower()}

    return {a for a in own if a}


# ── Разбор письма ──────────────────────────────────────────────────


class _Text(HTMLParser):
    """HTML → текст: абзацы и переносы, без стилей и скриптов."""

    _BREAKS: ClassVar[frozenset[str]] = frozenset(
        {"br", "p", "div", "tr", "li", "h1", "h2", "h3", "h4", "blockquote"}
    )

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("style", "script", "head"):
            self.skip += 1
        elif tag in self._BREAKS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("style", "script", "head"):
            self.skip = max(0, self.skip - 1)
        elif tag in ("p", "div", "tr", "blockquote"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.skip:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    parser = _Text()
    parser.feed(html)
    text = "".join(parser.parts).replace("\xa0", " ")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.splitlines()]

    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


#: С этой строки начинается цитата прошлой переписки
_QUOTE_STARTS = (
    re.compile(r"^>"),
    # «On Mon, 6 Oct 2026 at 10:00, Name <a@b> wrote:», «6 окт. 2026 г., в 10:00, … написал:»
    re.compile(r"^.{0,200}(wrote|написал|написала|пишет|yozdi)\s*:\s*$", re.IGNORECASE),
    re.compile(r"^-{2,}\s*(original message|исходное сообщение|пересылаемое сообщение)", re.I),
    re.compile(r"^_{10,}\s*$"),
    re.compile(r"^(from|от|кому|sent|отправлено):\s.+$", re.IGNORECASE),
)


def strip_quote(text: str) -> str:
    """Ответ без цитаты прошлой переписки; ничего не осталось — весь текст."""
    lines = text.splitlines()

    for number, line in enumerate(lines):
        if any(pattern.match(line.strip()) for pattern in _QUOTE_STARTS):
            head = "\n".join(lines[:number]).strip()

            return head or text.strip()

    return text.strip()


@dataclass
class Attachment:
    name: str
    content_type: str
    content: bytes


@dataclass
class Letter:
    """Письмо, разобранное до того, что нужно обращению."""

    message_id: str
    replies_to: list[str]
    from_name: str
    from_email: str
    subject: str
    text: str
    attachments: list[Attachment] = field(default_factory=list)
    automatic: bool = False
    bounce: bool = False
    raw: bytes = b""


def _ids(value: str | None) -> list[str]:
    return re.findall(r"<[^<>\s]+>", value or "")


def _header(message: EmailMessage, name: str) -> str:
    try:
        return str(message.get(name) or "")
    except (ValueError, TypeError, IndexError):
        # Кривой заголовок не должен ронять разбор всего письма
        raw = message.get_all(name, failobj=[])

        return str(raw[0]) if raw else ""


def _safe_name(name: str, number: int) -> str:
    cleaned = re.sub(r"[\x00-\x1f/\\\\:*?\"<>|]+", "_", name or "").strip(" ._")

    return cleaned[:150] or f"file-{number}"


def parse(raw: bytes) -> Letter:
    message = message_from_bytes(raw, policy=policy.default)
    assert isinstance(message, EmailMessage)
    from_name, from_email = parseaddr(_header(message, "From"))
    subject = " ".join(_header(message, "Subject").split())
    body = message.get_body(preferencelist=("plain", "html"))
    text = ""

    if body is not None:
        try:
            content = body.get_content()
        except (LookupError, ValueError):
            payload = body.get_payload(decode=True)
            content = payload.decode("utf-8", "replace") if isinstance(payload, bytes) else ""

        text = html_to_text(content) if body.get_content_type() == "text/html" else str(content)

    attachments: list[Attachment] = []

    for number, part in enumerate(message.iter_attachments(), 1):
        payload = part.get_payload(decode=True)

        if not isinstance(payload, bytes) or not payload:
            continue

        kind = part.get_content_type()

        if kind.startswith("image/") and len(payload) < MIN_IMAGE_BYTES:
            continue

        attachments.append(Attachment(_safe_name(part.get_filename() or "", number), kind, payload))

    automatic_header = _header(message, "Auto-Submitted").strip().lower()
    precedence = _header(message, "Precedence").strip().lower()
    local = from_email.split("@", 1)[0].lower()
    bounce = message.get_content_type() == "multipart/report" or local in _DAEMONS

    return Letter(
        message_id=(_ids(_header(message, "Message-ID")) or [""])[0][:255],
        replies_to=_ids(_header(message, "In-Reply-To")) + _ids(_header(message, "References")),
        from_name=" ".join(from_name.split())[:160],
        from_email=from_email.strip().lower()[:160],
        subject=subject,
        text=text.replace("\r\n", "\n").strip(),
        attachments=attachments,
        automatic=bool(
            (automatic_header and automatic_header != "no")
            or precedence in ("bulk", "junk", "list", "auto_reply")
            or _header(message, "X-Autoreply")
            or _header(message, "X-Autorespond")
            or _header(message, "List-Unsubscribe")
        ),
        bounce=bounce,
        raw=raw,
    )


# ── Обращение ──────────────────────────────────────────────────────


def _user_by_email(email: str) -> tuple[int | None, int | None]:
    with connection.cursor() as cursor:
        cursor.execute(
            "select id, company_id from users where lower(email) = %s and deleted_at is null "
            "order by id limit 1",
            [email.lower()],
        )
        row = cursor.fetchone()

    return (int(row[0]), row[1]) if row else (None, None)


def _same_person(ticket: Ticket, email: str) -> bool:
    if (ticket.author_email or "").lower() == email:
        return True

    user = ticket.user

    return user is not None and (user.email or "").lower() == email


def thread_of(letter: Letter) -> Ticket | None:
    """Обращение, которое письмо продолжает, — если пишет тот же человек."""
    candidates: list[int] = []

    for message_id in letter.replies_to:
        if match := _OUR_ID.fullmatch(message_id):
            candidates.append(int(match.group(1)))

    if letter.replies_to:
        earlier = (
            Message.objects.filter(email_message_id__in=letter.replies_to[:50])
            .order_by("-id")
            .values_list("ticket_id", flat=True)
        )
        candidates += [int(pk) for pk in earlier]

    if match := _TAG.search(letter.subject):
        candidates.append(int(match.group(1)))

    for pk in dict.fromkeys(candidates):
        ticket: Ticket | None = Ticket.objects.filter(pk=pk).select_related("user").first()

        if ticket is not None and _same_person(ticket, letter.from_email):
            return ticket

    return None


def _store(ticket_id: int, attachments: list[Attachment]) -> tuple[list[dict[str, Any]], list[str]]:
    """Вложения — в закрытое хранилище; что не влезло — заметкой."""
    saved: list[dict[str, Any]] = []
    notes: list[str] = []
    total = 0
    folder = private_root() / "support" / str(ticket_id)

    for attachment in attachments:
        size = len(attachment.content)

        if len(saved) >= MAX_FILES:
            notes.append(f"«{attachment.name}»: больше {MAX_FILES} вложений — не сохранено")
            continue

        if size > MAX_FILE_BYTES or total + size > MAX_TOTAL_BYTES:
            notes.append(f"«{attachment.name}»: слишком большое — не сохранено")
            continue

        suffix = Path(attachment.name).suffix.lower()
        suffix = suffix if re.fullmatch(r"\.[a-z0-9]{1,10}", suffix) else ""
        relative = f"support/{ticket_id}/{secrets.token_hex(20)}{suffix}"
        folder.mkdir(parents=True, exist_ok=True)
        (private_root() / relative).write_bytes(attachment.content)
        total += size
        saved.append(
            {
                "name": attachment.name,
                "path": relative,
                "size": size,
                "type": attachment.content_type,
            }
        )

    return saved, notes


@dataclass
class Outcome:
    kind: str  # created, appended, skipped
    ticket_id: int | None = None
    reason: str = ""


def _bounce(letter: Letter) -> Outcome:
    """Отказ доставки нашего ответа — внутренней заметкой в его обращение."""
    match = _OUR_ID.search(letter.raw.decode("utf-8", "replace"))

    if match is None:
        return Outcome("skipped", reason="отказ доставки не нашему ответу")

    ticket = Ticket.objects.filter(pk=int(match.group(1))).first()

    if ticket is None:
        return Outcome("skipped", reason="отказ доставки: обращения нет")

    detail = " ".join(letter.text.split())[:500]
    Message(
        ticket_id=ticket.pk,
        from_staff=True,
        is_internal=True,
        body=f"Письмо клиенту не доставлено. {detail}".strip(),
        email_message_id=letter.message_id or None,
    ).save()

    return Outcome("appended", ticket.pk, "отказ доставки")


def accept(raw: bytes) -> Outcome:
    """Одно письмо: продолжение обращения, новое обращение или пропуск."""
    letter = parse(raw)

    if letter.message_id and Message.objects.filter(email_message_id=letter.message_id).exists():
        return Outcome("skipped", reason="уже загружено")

    if letter.bounce:
        return _bounce(letter)

    if not letter.from_email or "@" not in letter.from_email:
        return Outcome("skipped", reason="нет адреса отправителя")

    if letter.from_email in _ours():
        return Outcome("skipped", reason="письмо самим себе")

    if letter.automatic:
        return Outcome("skipped", reason="автоответ или рассылка")

    if _NO_REPLY.match(letter.from_email.split("@", 1)[0]):
        return Outcome("skipped", reason="адрес без ответа (no-reply)")

    if spam.is_blocked(letter.from_email):
        return Outcome("skipped", reason="отправитель в спам-фильтре")

    stamp = now()

    with transaction.atomic():
        ticket = thread_of(letter)
        created = ticket is None

        if ticket is None:
            user_id, company_id = _user_by_email(letter.from_email)
            subject = _TAG.sub("", letter.subject).strip() or "(без темы)"
            ticket = Ticket(
                subject=subject[:200],
                user_id=user_id,
                company_id=company_id,
                author_name=letter.from_name or letter.from_email.split("@", 1)[0],
                author_email=letter.from_email,
                status=STATUS_OPEN,
                channel="email",
                priority="normal",
                last_reply_at=stamp,
            )
            ticket.save()
            text = letter.text
        else:
            # Клиент ответил: ждавшее его или закрытое — снова в работу
            if ticket.status in (STATUS_WAITING, STATUS_CLOSED):
                ticket.status = STATUS_WORKING if ticket.assignee_id else STATUS_OPEN

            ticket.last_reply_at = stamp
            ticket.save()
            text = strip_quote(letter.text)

        saved, notes = _store(int(ticket.pk), letter.attachments)
        body = text[:MAX_BODY] or ("(письмо без текста)" if not saved else "(вложения)")

        if notes:
            body += "\n\n— " + "\n— ".join(notes)

        Message(
            ticket_id=ticket.pk,
            author_id=ticket.user_id if ticket.user_id else None,
            from_staff=False,
            is_internal=False,
            body=body,
            attachments=saved or None,
            email_message_id=letter.message_id or None,
        ).save()

    if created:
        audit.record(
            connection,
            action="created",
            section="support",
            actor=None,
            subject_type=TICKET_MODEL,
            subject_id=ticket.pk,
            subject_label=ticket.subject,
            note=f"Письмо от {letter.from_email}",
        )

    return Outcome("created" if created else "appended", int(ticket.pk))


# ── Ящик ───────────────────────────────────────────────────────────


@dataclass
class Pass:
    created: int = 0
    appended: int = 0
    skipped: int = 0
    failed: int = 0

    def __bool__(self) -> bool:
        return bool(self.created or self.appended or self.skipped or self.failed)

    def __str__(self) -> str:
        return (
            f"новых {self.created}, в обращения {self.appended}, "
            f"пропущено {self.skipped}, ошибок {self.failed}"
        )


def run(limit: int = LIMIT) -> Pass:
    """Проход по непрочитанным письмам ящика поддержки."""
    settings = imap()
    report = Pass()

    if settings is None:
        return report

    with imaplib.IMAP4_SSL(settings.host, settings.port, timeout=30) as box:
        box.login(settings.username, settings.password)
        box.select(settings.folder)
        _, found = box.uid("search", None, "UNSEEN")  # type: ignore[arg-type]
        uids = (found[0] or b"").split()[:limit] if found else []

        for uid in uids:
            _, fetched = box.uid("fetch", uid.decode(), "(BODY.PEEK[])")
            raw = next(
                (item[1] for item in fetched or [] if isinstance(item, tuple) and len(item) > 1),
                None,
            )

            if not isinstance(raw, bytes):
                continue

            try:
                outcome = accept(raw)
            except Exception:
                log.exception("Письмо в ящике поддержки не разобрано (UID %s)", uid)
                box.uid("store", uid.decode(), "+FLAGS", "(\\Flagged)")
                report.failed += 1
            else:
                setattr(report, outcome.kind, getattr(report, outcome.kind) + 1)

            box.uid("store", uid.decode(), "+FLAGS", "(\\Seen)")

    return report


# ── Ответ клиенту ──────────────────────────────────────────────────


def recipient(ticket: Ticket) -> str | None:
    """Кому писать: почта из обращения, иначе — учётной записи."""
    if ticket.author_email:
        return str(ticket.author_email)

    user = ticket.user

    return str(user.email) if user is not None and user.email else None


def _domain(email: str) -> str:
    return email.rsplit("@", 1)[-1] if "@" in email else "savdex.uz"


def reply(ticket: Ticket, message: Message) -> tuple[bool, str]:
    """
    Ответ поддержки — письмом клиенту. (ушло ли, кому или почему нет);
    итог — в самом сообщении: emailed_at или email_error.
    """
    to = recipient(ticket)

    if not to:
        return False, "у обращения нет почты клиента"

    support = address()
    subject = ticket.subject if _TAG.search(ticket.subject) else f"{ticket.subject} [№{ticket.pk}]"
    subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    message_id = f"<support-{ticket.pk}-{message.pk}.{secrets.token_hex(6)}@{_domain(support)}>"
    previous = list(
        Message.objects.filter(ticket_id=ticket.pk, from_staff=False)
        .exclude(email_message_id__isnull=True)
        .order_by("-id")
        .values_list("email_message_id", flat=True)[:1]
    )
    headers = {"Message-ID": message_id}

    if previous and previous[0]:
        headers["In-Reply-To"] = str(previous[0])
        headers["References"] = str(previous[0])

    app_url = (os.environ.get("APP_URL") or "https://savdex.uz").rstrip("/")
    footer = (
        f"Поддержка SavdEx · {app_url}\n"
        f"Обращение №{ticket.pk}. Чтобы дополнить — просто ответьте на это письмо."
    )
    text = f"{message.body.strip()}\n\n—\n{footer}\n"
    page = (
        '<!doctype html><html><body style="margin:0;padding:24px;background:#f4f5f7;">'
        '<div style="max-width:600px;margin:0 auto;background:#ffffff;border-radius:8px;'
        "padding:28px 32px;font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,"
        'Helvetica,Arial,sans-serif;">'
        + mail.paragraphs(message.body)
        + '</div><p style="max-width:600px;margin:16px auto 0;font-family:Arial,sans-serif;'
        'font-size:12px;line-height:1.5;color:#6b7280;text-align:center;">'
        + mail.paragraphs(footer).replace("font-size:15px", "font-size:12px")
        + "</p></body></html>"
    )
    ok = mail.send(
        to,
        subject,
        page,
        text,
        reply_to=support,
        headers=headers,
        prefix=_prefix(),
        sender=formataddr(("SavdEx — поддержка", support)),
    )
    stamp = timezone.now().replace(microsecond=0)

    if ok:
        Message.objects.filter(pk=message.pk).update(
            email_message_id=message_id, emailed_at=stamp, email_error=None
        )

        return True, to

    Message.objects.filter(pk=message.pk).update(email_error="почтовик не принял письмо")

    return False, "почтовик не принял письмо"


# ── Для проверок и ручной загрузки ─────────────────────────────────


def recipients_of(raw: bytes) -> list[str]:
    """Адреса «Кому» и «Копия» письма (для проверок)."""
    message = message_from_bytes(raw, policy=policy.default)

    headers = message.get_all("To", []) + message.get_all("Cc", [])

    return [a.lower() for _, a in getaddresses(headers)]
