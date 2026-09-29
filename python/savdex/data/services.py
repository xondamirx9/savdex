"""
Решения по объявлениям и их фотографии — копия действий ListingsTable и
ImagesRelationManager. Запись — общими частями сайта (save_listing,
уведомление компании, ImageStore), журнал — как AuditObserver у Listing.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.core.files.uploadedfile import UploadedFile
from django.db import connection
from django.http import HttpRequest

from savdex.data.models import LIFETIME_DAYS, Listing
from savdex.guards import allowed_writes
from savdex.moderation.services import context_of, notify_company
from savdex.web import eloquent, image_store
from savdex.web.cabinet import _rows
from savdex.web.listing_actions import _now, _stamp, save_listing
from savdex.web.listing_image_actions import _images, _resequence, _set_sort


def _row(listing: Listing) -> dict[str, Any]:
    return _rows("select * from listings where id = %s", [listing.pk])[0]


def _decide(
    request: HttpRequest,
    listing: Listing,
    changes: dict[str, Any],
    title: str,
    tone: str,
    url: str,
    body: str | None,
) -> None:
    ctx = context_of(request)
    row = _row(listing)
    save_listing(ctx, row, changes)

    if row["company_id"] is not None:
        notify_company(ctx, row["company_id"], "moderation", title, tone, url, body)


def approve_listing(request: HttpRequest, listing: Listing) -> None:
    """Одобрить: на витрину, дата публикации и срок — если их не было."""
    row = _row(listing)
    now = _now()
    _decide(
        request,
        listing,
        {
            "status": "active",
            "moderation_note": None,
            "published_at": row["published_at"] or now,
            "expires_at": row["expires_at"] or now + timedelta(days=LIFETIME_DAYS),
        },
        f"Объявление «{listing.title}» опубликовано",
        "success",
        "/cabinet/listings",
        None,
    )


def return_listing(request: HttpRequest, listing: Listing, reason: str) -> None:
    """Вернуть на исправление: автор правит это же объявление и публикует снова."""
    _decide(
        request,
        listing,
        {"status": "needs_changes", "moderation_note": reason},
        f"Объявление «{listing.title}» возвращено на исправление",
        "warning",
        "/cabinet/listings?status=needs_changes",
        reason,
    )


def reject_listing(request: HttpRequest, listing: Listing, reason: str) -> None:
    """Отклонить: это объявление на витрину не вернётся."""
    _decide(
        request,
        listing,
        {"status": "rejected", "moderation_note": reason},
        f"Объявление «{listing.title}» отклонено",
        "danger",
        "/cabinet/listings?status=rejected",
        reason,
    )


def add_photos(listing_id: int, files: list[UploadedFile[bytes]]) -> int:
    """
    Загрузка из админки: та же обработка, что у владельца (пережатие и
    миниатюра), после последней; не изображение — пропускается.
    """
    sort = max((image["sort"] for image in _images(listing_id)), default=-1) + 1
    saved = 0

    for file in files:
        if file.size is not None and file.size > 8 * 1024 * 1024:
            continue

        try:
            paths = image_store.store_with_thumb(file.read(), f"listings/{listing_id}")
        except image_store.UnreadableImageError:
            continue

        now = _stamp(eloquent.now())

        with allowed_writes("listing_images"), connection.cursor() as cursor:
            cursor.execute(
                "insert into listing_images (listing_id, path, thumb_path, sort, updated_at, "
                "created_at) values (%s, %s, %s, %s, %s, %s)",
                [listing_id, paths["path"], paths["thumb_path"], sort, now, now],
            )

        sort += 1
        saved += 1

    return saved


def photo_action(listing_id: int, image_id: int, todo: str) -> bool:
    """«Сделать обложкой» или «Удалить» (файлы с диска вместе с миниатюрой)."""
    image = next((i for i in _images(listing_id) if i["id"] == image_id), None)

    if image is None:
        return False

    if todo == "cover":
        _set_sort(image, -1)
        _resequence(listing_id)

        return True

    image_store.delete(image["path"], image["thumb_path"])

    with allowed_writes("listing_images"), connection.cursor() as cursor:
        cursor.execute("delete from listing_images where id = %s", [image_id])

    _resequence(listing_id)

    return True


def force_delete_listing(listing: Listing) -> None:
    """ForceDeleteAction: строки — прочь (фото и связанное база уберёт сама), файлы — с диска."""
    for image in _images(listing.pk):
        image_store.delete(image["path"], image["thumb_path"])

    with allowed_writes("listings"), connection.cursor() as cursor:
        cursor.execute("delete from listings where id = %s", [listing.pk])
