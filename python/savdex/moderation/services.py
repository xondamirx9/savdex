"""
Решения модератора по отзывам — копия ModerationService (отзывы о
компаниях) и PlatformReviewService (отзывы о площадке).

Порядок — как у Laravel: запись и пересчёт рейтинга, потом уведомления,
потом строка журнала о решении. Правка отзыва пишет в журнал ещё и
«изменено» (AuditObserver у Review); у отзыва о площадке наблюдателя нет.

Одно отличие: рейтинг компании пересчитывается один раз. У Laravel —
дважды (событие saved и сама служба), и при смене оценки в журнале две
одинаковые строки о компании.

Общие части сайта (пересчёт рейтинга, уведомления, журнал правок чужих
таблиц) ждут контекст запроса сайта; раздел передаёт им AdminContext —
вошедшего сотрудника и запрос.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

from django.db import connection, transaction
from django.http import HttpRequest

from savdex import audit
from savdex.adminsite import SavdexModelAdmin, _admin_of
from savdex.catalog import now
from savdex.guards import allowed_writes
from savdex.moderation.models import (
    DOC_APPROVED,
    DOC_REJECTED,
    HIDDEN,
    PUBLISHED,
    RESUME_BLOCKED,
    RESUME_PUBLISHED,
    CompanyDocument,
    PlatformReview,
    Resume,
    Review,
)
from savdex.web import ui
from savdex.web.cabinet import _rows
from savdex.web.chat_actions import str_limit
from savdex.web.listing_actions import Text, _notify_company
from savdex.web.review_actions import recalculate
from savdex.web.shared import Context


@dataclass
class AdminContext:
    """
    Сколько нужно общим частям сайта: кто действует, сам запрос и язык
    текстов (админка русская — уведомления от её имени тоже).
    """

    request: HttpRequest
    user: dict[str, Any]
    locale: str = "ru"

    def t(self, key: str, **replace: object) -> str:
        """Context.t: строка словаря сайта."""
        from savdex.web import ui

        return ui.t(key, self.locale, **replace)


def context_of(request: HttpRequest) -> Context:
    staff = _admin_of(request)
    ctx = AdminContext(
        request=request,
        user={"id": staff.id, "name": staff.name, "email": staff.email, "is_admin": True},
    )

    return cast(Context, ctx)


def live_company(company_id: int | None) -> dict[str, Any] | None:
    """Company::find: компания без мягкого удаления — вся строка."""
    if company_id is None:
        return None

    rows = _rows("select * from companies where id = %s and deleted_at is null", [company_id])

    return rows[0] if rows else None


def recalculate_companies(ctx: Context, *company_ids: int | None) -> None:
    """ReviewService::recalculate по каждой (без повторов), кроме удалённых."""
    seen: set[int] = set()

    for company_id in company_ids:
        if company_id is None or company_id in seen:
            continue

        seen.add(company_id)
        company = live_company(company_id)

        if company is not None:
            recalculate(ctx, company)


def notify_company(
    ctx: Context,
    company_id: int,
    type_: str,
    title: Text,
    tone: str,
    url: str | None,
    body: Text | None,
) -> None:
    """Notifier::company: лента кабинета и уведомление каждому сотруднику на его языке."""
    _notify_company(ctx, {"id": company_id}, type_, title, tone, cast(str, url), body)


def notify_user(
    user_id: int, type_: str, title: str, tone: str, url: str | None, body: str | None = None
) -> None:
    """Notifier::user — UserNotification::deliver: компания — с пользователя."""
    rows = _rows("select id, company_id from users where id = %s and deleted_at is null", [user_id])

    if not rows:
        return

    stamp = now().strftime("%Y-%m-%d %H:%M:%S")

    with allowed_writes("user_notifications"), connection.cursor() as cursor:
        cursor.execute(
            "insert into user_notifications (user_id, company_id, type, title, tone, url, body, "
            "created_at, updated_at) values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [user_id, rows[0]["company_id"], type_, title, tone, url, body, stamp, stamp],
        )


def _decision(
    request: HttpRequest,
    action: str,
    subject: Review | PlatformReview | CompanyDocument | Resume,
    laravel_model: str,
    note: str | None,
    section: str = "reviews",
) -> None:
    """AdminLog::record: решение по существу, с формулировкой."""
    audit.record(
        connection,
        action=action,
        section=section,
        actor=_admin_of(request),
        subject_type=laravel_model,
        subject_id=subject.pk,
        subject_label=audit.label(
            SavdexModelAdmin.attributes(subject), laravel_model.rsplit("\\", 1)[-1], subject.pk
        ),
        changes=None,
        note=note,
        ip=audit.client_ip(request),
    )


# ── Отзывы о компаниях ───────────────────────────────────────────────

REVIEW = "App\\Models\\Review"


def _save_review(request: HttpRequest, review: Review, changes: dict[str, Any]) -> bool:
    """
    forceFill($changes)->save(): запись, строка «изменено» (AuditObserver);
    вернуть, нужен ли пересчёт (Review::saved — оценка, статус, компания).
    """
    before = SavdexModelAdmin.attributes(review)

    for field, value in changes.items():
        setattr(review, field, value)

    with allowed_writes("reviews"):
        review.save()

    after = SavdexModelAdmin.attributes(review)
    changed = {k: v for k, v in after.items() if before.get(k) != v and k not in audit.NOISE}

    if changed:
        audit.record(
            connection,
            action="updated",
            section="reviews",
            actor=_admin_of(request),
            subject_type=REVIEW,
            subject_id=review.pk,
            subject_label=audit.label(after, "Review", review.pk),
            changes={"before": {k: before.get(k) for k in changed}, "after": changed},
            ip=audit.client_ip(request),
        )

    return bool({"rating", "status", "company_id"} & set(changed))


def _fields(changes: dict[str, Any]) -> list[str]:
    """Имена полей для update_fields: роль правит только выданные столбцы."""
    return [name.removesuffix("_id") if name.endswith("_by_id") else name for name in changes]


def _decided(request: HttpRequest, **fields: Any) -> dict[str, Any]:
    return {**fields, "moderated_by_id": _admin_of(request).id, "moderated_at": now()}


def approve_review(request: HttpRequest, review: Review) -> None:
    """Отзыв прошёл проверку: на витрину, компании — уведомление."""
    ctx = context_of(request)

    with transaction.atomic():
        if _save_review(request, review, _decided(request, status=PUBLISHED)):
            recalculate_companies(ctx, review.company_id)

    author = live_company(review.author_company_id)

    if author is not None and live_company(review.company_id) is not None:
        # ReviewService::publishedNotice
        notify_company(
            ctx,
            review.company_id,
            "review",
            lambda locale: ui.t(
                "messages.review.notify_title",
                locale,
                company=author["name"],
                rating=review.rating,
            ),
            "success" if review.rating >= 4 else "warning",
            "/cabinet/reviews",
            str_limit(review.body, 140),
        )

    _decision(request, "approved", review, REVIEW, None)


def reject_review(request: HttpRequest, review: Review, note: str) -> None:
    """Отзыв не пропущен: автору — причина словами модератора."""
    ctx = context_of(request)

    with transaction.atomic():
        if _save_review(request, review, _decided(request, status=HIDDEN, moderator_note=note)):
            recalculate_companies(ctx, review.company_id)

    if live_company(review.author_company_id) is not None:
        notify_company(
            ctx,
            review.author_company_id,
            "moderation",
            lambda locale: ui.t("messages.moderation.review_rejected", locale),
            "warning",
            None,
            note,
        )

    _decision(request, "rejected", review, REVIEW, note)


def accept_dispute(request: HttpRequest, review: Review, note: str) -> None:
    """Спор удовлетворён: отзыв скрыт; уведомлены обе стороны."""
    ctx = context_of(request)
    changes = _decided(request, status=HIDDEN, dispute_status="accepted", moderator_note=note)

    with transaction.atomic():
        if _save_review(request, review, changes):
            recalculate_companies(ctx, review.company_id)

    if live_company(review.company_id) is not None:
        notify_company(
            ctx,
            review.company_id,
            "moderation",
            lambda locale: ui.t("messages.moderation.dispute_accepted", locale),
            "success",
            "/cabinet/reviews",
            note,
        )

    if live_company(review.author_company_id) is not None:
        notify_company(
            ctx,
            review.author_company_id,
            "moderation",
            lambda locale: ui.t("messages.moderation.review_hidden", locale),
            "warning",
            None,
            note,
        )

    # В журнале — что случилось с записью: искать будут «куда делся отзыв»
    _decision(request, "hidden", review, REVIEW, note)


def decline_dispute(request: HttpRequest, review: Review, note: str) -> None:
    """Спор отклонён: отзыв остаётся, компании — объяснение."""
    ctx = context_of(request)
    _save_review(request, review, _decided(request, dispute_status="declined", moderator_note=note))

    if live_company(review.company_id) is not None:
        notify_company(
            ctx,
            review.company_id,
            "moderation",
            lambda locale: ui.t("messages.moderation.dispute_declined", locale),
            "warning",
            "/cabinet/reviews",
            note,
        )

    _decision(request, "rejected", review, REVIEW, note)


def restore_review(request: HttpRequest, review: Review) -> None:
    """Вернуть скрытый на витрину: решение бывает ошибочным."""
    ctx = context_of(request)

    with transaction.atomic():
        if _save_review(
            request, review, _decided(request, status=PUBLISHED, dispute_status="declined")
        ):
            recalculate_companies(ctx, review.company_id)

    _decision(request, "restored", review, REVIEW, None)


# ── Отзывы о площадке ────────────────────────────────────────────────

PLATFORM = "App\\Models\\PlatformReview"


def _decide_platform(
    request: HttpRequest, review: PlatformReview, status: str, note: str | None
) -> None:
    """PlatformReviewService::decide — forceFill и save; наблюдателя нет."""
    review.status = status
    review.moderator_note = note
    review.moderated_by_id = _admin_of(request).id
    review.moderated_at = now()

    with allowed_writes("platform_reviews"):
        review.save(
            update_fields=["status", "moderator_note", "moderated_by", "moderated_at", "updated_at"]
        )


def _author_locale(review: PlatformReview) -> tuple[int, str] | None:
    """Автор (не удалён) и его язык — уведомление пишется на нём."""
    if review.user_id is None:
        return None

    rows = _rows(
        "select id, locale from users where id = %s and deleted_at is null", [review.user_id]
    )

    return (rows[0]["id"], rows[0]["locale"] or "ru") if rows else None


def approve_platform(request: HttpRequest, review: PlatformReview) -> None:
    _decide_platform(request, review, PUBLISHED, None)
    author = _author_locale(review)

    if author is not None:
        notify_user(
            author[0],
            "review",
            ui.t("platform_reviews.notice_published", author[1]),
            "success",
            "/reviews?type=platform",
        )

    _decision(request, "approved", review, PLATFORM, None)


def reject_platform(request: HttpRequest, review: PlatformReview, note: str) -> None:
    _decide_platform(request, review, HIDDEN, note)
    author = _author_locale(review)

    if author is not None:
        notify_user(
            author[0],
            "moderation",
            ui.t("platform_reviews.notice_rejected", author[1]),
            "warning",
            "/reviews/new",
            note,
        )

    _decision(request, "rejected", review, PLATFORM, note)


def restore_platform(request: HttpRequest, review: PlatformReview) -> None:
    _decide_platform(request, review, PUBLISHED, None)
    _decision(request, "restored", review, PLATFORM, None)


# ── Документы на проверку ────────────────────────────────────────────

DOCUMENT = "App\\Models\\CompanyDocument"


def _save_document(
    request: HttpRequest, document: CompanyDocument, changes: dict[str, Any]
) -> None:
    """forceFill($changes)->save() и строка «изменено» (AuditObserver, documents)."""
    before = SavdexModelAdmin.attributes(document)

    for field, value in changes.items():
        setattr(document, field, value)

    with allowed_writes("company_documents"):
        document.save(update_fields=[*_fields(changes), "updated_at"])

    after = SavdexModelAdmin.attributes(document)
    changed = {k: v for k, v in after.items() if before.get(k) != v and k not in audit.NOISE}

    if changed:
        audit.record(
            connection,
            action="updated",
            section="documents",
            actor=_admin_of(request),
            subject_type=DOCUMENT,
            subject_id=document.pk,
            subject_label=audit.label(after, "CompanyDocument", document.pk),
            changes={"before": {k: before.get(k) for k in changed}, "after": changed},
            ip=audit.client_ip(request),
        )


def approve_document(request: HttpRequest, document: CompanyDocument) -> None:
    """Документ принят: на визитке, если компания разрешила показ."""
    ctx = context_of(request)
    _save_document(
        request,
        document,
        _decided(request, moderation_status=DOC_APPROVED, moderation_note=None),
    )

    if document.company_id is not None and live_company(document.company_id) is not None:
        notify_company(
            ctx,
            document.company_id,
            "moderation",
            lambda locale: ui.t(
                "messages.moderation.document_approved", locale, title=document.title
            ),
            "success",
            "/cabinet/company",
            None,
        )

    _decision(request, "approved", document, DOCUMENT, None, section="documents")


def reject_document(request: HttpRequest, document: CompanyDocument, reason: str) -> None:
    """Документ отклонён: без причины человек пришлёт тот же файл."""
    ctx = context_of(request)
    _save_document(
        request,
        document,
        _decided(request, moderation_status=DOC_REJECTED, moderation_note=reason),
    )

    if document.company_id is not None and live_company(document.company_id) is not None:
        notify_company(
            ctx,
            document.company_id,
            "moderation",
            lambda locale: ui.t(
                "messages.moderation.document_rejected", locale, title=document.title
            ),
            "danger",
            "/cabinet/company",
            reason,
        )

    _decision(request, "rejected", document, DOCUMENT, reason, section="documents")


# ── Резюме ───────────────────────────────────────────────────────────

RESUME = "App\\Models\\Resume"


def _save_resume(resume: Resume, changes: dict[str, Any]) -> None:
    """
    forceFill($changes)->save(): статус, заметка, дата публикации. Resume::saving
    сбрасывает переводы только при смене текста — здесь его не трогают;
    перевод вернувшегося резюме подбирает обработчик Python.
    """
    for field, value in changes.items():
        setattr(resume, field, value)

    with allowed_writes("resumes"):
        resume.save(update_fields=[*_fields(changes), "updated_at"])


def block_resume(request: HttpRequest, resume: Resume, note: str) -> None:
    """Снять с публикации: причину видит соискатель в кабинете."""
    _save_resume(resume, {"status": RESUME_BLOCKED, "moderation_note": note})
    _decision(request, "hidden", resume, RESUME, note, section="resumes")


def restore_resume(request: HttpRequest, resume: Resume) -> None:
    """Вернуть в раздел: заметка модерации снимается."""
    _save_resume(
        resume,
        {
            "status": RESUME_PUBLISHED,
            "published_at": resume.published_at or now(),
            "moderation_note": None,
        },
    )
    _decision(request, "restored", resume, RESUME, None, section="resumes")
