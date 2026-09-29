"""
Фото объявления — формы на Django (этап 5, шаг 37): загрузить пачкой,
удалить, сделать обложкой. Копия App\\Http\\Controllers\\Cabinet\\ListingImageController.

Посредник verified, как у группы маршрутов мастера. Пачка режется до
свободных мест (не больше 10 фото), битый файл пропускается, остальные
сохраняются — фото и превью (ImageStore::storeWithThumb). После удаления
и перестановки фото нумеруются заново от нуля.

Сверка с настоящим Laravel — tests/test_web_listing_image_actions.py.
"""

from __future__ import annotations

from typing import Any

from django.db import connection
from django.http import HttpRequest, HttpResponse

from savdex.guards import allowed_writes
from savdex.web import eloquent, image_store
from savdex.web.actions import form
from savdex.web.cabinet import _rows, company_of
from savdex.web.chat_actions import _unverified
from savdex.web.forms import action, back, flash, input_of, invalid
from savdex.web.listing_actions import _stamp
from savdex.web.shared import Context
from savdex.web.validation import validate
from savdex.web.views import not_found

#: Listing::MAX_IMAGES
MAX_IMAGES = 10


def _owned(ctx: Context, listing_id: int) -> dict[str, Any] | None:
    """ListingImageController::owned: своё объявление не в корзине."""
    company = company_of(ctx)

    if company is None:
        return None

    rows = _rows(
        "select * from listings where company_id = %s and id = %s and deleted_at is null",
        [company["id"], listing_id],
    )

    return rows[0] if rows else None


def _images(listing_id: int) -> list[dict[str, Any]]:
    """$listing->images(): по sort."""
    return _rows(
        "select * from listing_images where listing_id = %s order by sort, id", [listing_id]
    )


def _set_sort(image: dict[str, Any], sort: int) -> None:
    """$image->forceFill(['sort' => …])->save(): запись только при изменении."""
    if image["sort"] == sort:
        return

    now = _stamp(eloquent.now())

    with allowed_writes("listing_images"), connection.cursor() as cursor:
        cursor.execute(
            "update listing_images set sort = %s, updated_at = %s where id = %s",
            [sort, now, image["id"]],
        )


def _resequence(listing_id: int) -> None:
    """ListingImageController::resequence: номера от нуля по порядку."""
    for index, image in enumerate(_images(listing_id)):
        if image["sort"] != index:
            _set_sort(image, index)


def _files(request: HttpRequest) -> list[Any]:
    """$request->file('images'): images[] или images[0], images[1]…"""
    files = list(request.FILES.getlist("images[]"))
    indexed = sorted(
        (k for k in request.FILES if k.startswith("images[") and k != "images[]"),
        key=lambda k: k,
    )

    for key in indexed:
        files += request.FILES.getlist(key)

    return files


@form()
def store(request: HttpRequest, listing_id: str) -> HttpResponse:
    """ListingImageController::store (verified, throttle:30,60)."""
    ctx = action(request, throttle=30, throttle_minutes=60, throttle_prefix="listing-image")

    if (refused := _unverified(ctx)) is not None:
        return refused

    listing = _owned(ctx, int(listing_id))

    if listing is None:
        return not_found(ctx)

    files = _files(request)
    data: dict[str, Any] = {**input_of(request)}

    if files:
        data["images"] = files

    errors = validate(
        data,
        {
            "images": ["required", "array", f"max:{MAX_IMAGES}"],
            "images.*": ["file", "mimes:jpg,jpeg,png,webp", "max:8192"],
        },
        ctx.locale,
        {
            "images.required": ctx.t("messages.image.required"),
            "images.*.mimes": ctx.t("messages.image.mimes"),
            "images.*.max": ctx.t("messages.image.max"),
        },
    )

    if errors:
        return invalid(ctx, errors)

    already = len(_images(listing["id"]))
    free = MAX_IMAGES - already

    if free <= 0:
        flash(ctx, "error", ctx.t("messages.image.limit", max=MAX_IMAGES))

        return back(ctx)

    saved = 0

    for file in files[:free]:
        try:
            paths = image_store.store_with_thumb(file.read(), f"listings/{listing['id']}")
        except image_store.UnreadableImageError:
            # Один битый файл не должен рушить загрузку остальных
            continue

        now = _stamp(eloquent.now())

        with allowed_writes("listing_images"), connection.cursor() as cursor:
            cursor.execute(
                "insert into listing_images (listing_id, path, thumb_path, sort, updated_at, "
                "created_at) values (%s, %s, %s, %s, %s, %s)",
                [listing["id"], paths["path"], paths["thumb_path"], already + saved, now, now],
            )

        saved += 1

    if saved == 0:
        flash(ctx, "error", ctx.t("messages.image.none_readable"))

        return back(ctx)

    skipped = len(files) - saved

    if skipped > 0:
        flash(
            ctx,
            "success",
            ctx.t("messages.image.uploaded_skipped", saved=saved, skipped=skipped),
        )
    else:
        flash(ctx, "success", ctx.t("messages.image.uploaded", saved=saved))

    return back(ctx)


def _image(ctx: Context, listing_id: str, image_id: str) -> tuple[Any, HttpResponse | None]:
    if (refused := _unverified(ctx)) is not None:
        return None, refused

    listing = _owned(ctx, int(listing_id))

    if listing is None:
        return None, not_found(ctx)

    found = _rows(
        "select * from listing_images where listing_id = %s and id = %s",
        [listing["id"], int(image_id)],
    )

    return (found[0], None) if found else (None, not_found(ctx))


@form("DELETE")
def destroy(request: HttpRequest, listing_id: str, image_id: str) -> HttpResponse:
    """ListingImageController::destroy: файлы с диска, строку — прочь, номера заново."""
    ctx = action(request)
    image, refused = _image(ctx, listing_id, image_id)

    if refused is not None:
        return refused

    image_store.delete(image["path"], image["thumb_path"])

    with allowed_writes("listing_images"), connection.cursor() as cursor:
        cursor.execute("delete from listing_images where id = %s", [image["id"]])

    _resequence(image["listing_id"])
    flash(ctx, "success", ctx.t("messages.image.deleted"))

    return back(ctx)


@form()
def cover(request: HttpRequest, listing_id: str, image_id: str) -> HttpResponse:
    """ListingImageController::makeCover: первой, затем номера заново."""
    ctx = action(request)
    image, refused = _image(ctx, listing_id, image_id)

    if refused is not None:
        return refused

    _set_sort(image, -1)
    _resequence(image["listing_id"])
    flash(ctx, "success", ctx.t("messages.image.cover_set"))

    return back(ctx)
