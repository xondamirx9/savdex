"""
Решения по компании из админки — копия действий CompaniesTable: уровень
проверки, партнёрство, логотип и обложка (ImageStore), блокировка,
скрытие с витрины, корзина; столбцы выгрузки — CompanyExporter.
"""

from __future__ import annotations

from typing import Any

from django.core.files.uploadedfile import UploadedFile
from django.db import connection
from django.http import HttpRequest
from django.utils import timezone

from savdex.adminsite import _admin_of
from savdex.data.models import COMPANY_HIDDEN, LEVELS, CompanyRecord
from savdex.guards import allowed_writes
from savdex.moderation.services import context_of, notify_company
from savdex.web import image_store


def _save(company: CompanyRecord, **changes: Any) -> None:
    for field, value in changes.items():
        setattr(company, field, value)

    company.save()


def verify(request: HttpRequest, company: CompanyRecord, level: int) -> None:
    """Уровень проверки — руками модератора; владельцу — уведомление."""
    _save(
        company,
        verification_level=level,
        verified_at=timezone.now().replace(microsecond=0) if level > 0 else None,
        verified_by=_admin_of(request).id if level > 0 else None,
    )
    notify_company(
        context_of(request),
        company.pk,
        "moderation",
        f"Компания прошла проверку: {LEVELS[level]}" if level > 0 else "Уровень верификации снят",
        "success" if level > 0 else "warning",
        "/cabinet/company",
        None,
    )


def partner(company: CompanyRecord, tier: str | None, sort: int) -> None:
    """Партнёрство: вид на странице «Партнёры» и порядок во вкладке."""
    _save(company, partner_tier=tier, partner_sort=max(0, sort))


def picture(company: CompanyRecord, kind: str, upload: UploadedFile[bytes] | None) -> str:
    """
    Логотип или обложка: файл — через ImageStore, как у владельца; без
    файла — снять (вернутся инициалы или фирменный градиент).
    Сообщение с точкой в конце — удалось, без точки — ошибка.
    """
    column = f"{kind}_path"
    previous = getattr(company, column)

    if upload is None:
        image_store.delete(previous)
        _save(company, **{column: None})

        return (
            "Логотип снят — снова инициалы."
            if kind == "logo"
            else "Обложка снята — снова градиент."
        )

    if upload.size is not None and upload.size > 8 * 1024 * 1024:
        return "Файл больше 8 МБ"

    try:
        path = image_store.store(
            upload.read(),
            f"companies/{company.pk}",
            image_store.LOGO if kind == "logo" else image_store.COVER,
        )
    except image_store.UnreadableImageError:
        return "Файл не удалось прочитать как изображение"

    _save(company, **{column: path})
    image_store.delete(previous)

    return "Логотип обновлён." if kind == "logo" else "Обложка обновлена."


def block(company: CompanyRecord, reason: str) -> None:
    """Блокировка с причиной: активные объявления уходят из выдачи (в «снятые»)."""
    now = timezone.now().replace(microsecond=0)
    _save(company, status="blocked", blocked_reason=reason, blocked_at=now)

    with allowed_writes("listings"), connection.cursor() as cursor:
        # Eloquent Builder::update — и updated_at
        cursor.execute(
            "update listings set status = 'archived', updated_at = %s "
            "where company_id = %s and status = 'active' and deleted_at is null",
            [now.replace(tzinfo=None), company.pk],
        )


def unblock(company: CompanyRecord) -> None:
    _save(company, status="active", blocked_reason=None, blocked_at=None)


def hide(company: CompanyRecord) -> None:
    """
    Скрыть с витрины — тестовую или пустую компанию (ТЗ-01, п.4). Витрина
    показывает только status = 'active', поэтому компания и её объявления
    пропадают из каталога, поиска и с главной. Объявления не трогаются, а
    вход в кабинет не закрывается: это не блокировка, и вернуть всё можно
    одной кнопкой.
    """
    _save(company, status=COMPANY_HIDDEN)


def show(company: CompanyRecord) -> None:
    _save(company, status="active")


def restore(company: CompanyRecord) -> None:
    """RestoreAction: из корзины."""
    stamp = timezone.now().replace(microsecond=0)

    with allowed_writes("companies"):
        CompanyRecord.objects.filter(pk=company.pk).update(deleted_at=None, updated_at=stamp)


def force_delete(company: CompanyRecord) -> None:
    """ForceDeleteAction: строку — прочь, связанное база уберёт или обнулит сама."""
    image_store.delete(company.logo_path, company.cover_path)

    with allowed_writes("companies"), connection.cursor() as cursor:
        cursor.execute("delete from companies where id = %s", [company.pk])


def export_columns() -> list[tuple[str, Any]]:
    """CompanyExporter::getColumns."""
    from savdex.data.models import Listing
    from savdex.geo.models import City

    cities: dict[int, str] = {}

    def city(record: CompanyRecord) -> str | None:
        if record.city_id is None:
            return None

        if record.city_id not in cities:
            found = City.objects.filter(pk=record.city_id).first()
            cities[record.city_id] = found.name() if found is not None else ""

        return cities[record.city_id] or None

    return [
        ("ИНН", lambda r: r.tin),
        ("Название", lambda r: r.name),
        ("Юридическое название", lambda r: r.legal_name),
        ("Тип компании", lambda r: r.type),
        ("Город", city),
        ("Адрес", lambda r: r.address),
        ("Телефон", lambda r: r.phone),
        ("Почта", lambda r: r.email),
        ("Сайт", lambda r: r.website),
        ("Описание", lambda r: r.description),
        ("Год основания", lambda r: r.founded_year),
        ("Сотрудников", lambda r: r.employees_range),
        ("Верификация", lambda r: LEVELS.get(int(r.verification_level or 0), "Не проверена")),
        ("Рейтинг", lambda r: r.rating),
        ("Отзывов", lambda r: r.reviews_count),
        (
            "Объявлений",
            lambda r: Listing.objects.filter(company_id=r.pk, deleted_at__isnull=True).count(),
        ),
        ("Статус", lambda r: "Активна" if r.status == "active" else "Заблокирована"),
        ("Дата регистрации", lambda r: r.created_at),
    ]
