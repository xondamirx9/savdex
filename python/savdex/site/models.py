"""
Настройки площадки — перешли к Django (этап 2).

Таблица создана миграцией Laravel
(database/migrations/2026_07_29_100300_create_cms_tables.php):
managed = False, схему по-прежнему меняет только Laravel.

Правила App\\Models\\Setting, которые иначе обошёл бы новый код:

- значение хранится в json: строка, число, флаг — как Laravel кладёт
  их приведением 'array';
- после любой правки сбрасывается кэш настроек Laravel (settings.all,
  на сутки): иначе сайт сутки показывал бы старое, и правка выглядела
  бы несохранившейся.
"""

from __future__ import annotations

from typing import Any

from django.db import models

from savdex import laravel_cache
from savdex.catalog import Timestamped

#: Setting::CACHE_KEY
CACHE_KEY = "settings.all"

#: Setting::GROUPS
GROUPS: dict[str, str] = {
    "general": "Общие",
    "appearance": "Оформление",
    "contacts": "Контакты",
    "legal": "Реквизиты",
    "social": "Соцсети",
    "limits": "Ограничения",
    "moderation": "Модерация",
    "currency": "Валюты",
}

#: Типы значения. «boolean» — так флаг премодерации отзывов завела
#: миграция; форма Filament знала только «bool» и поля для него не
#: показывала вовсе — переключить премодерацию из админки было нельзя
TYPES: dict[str, str] = {
    "string": "Строка",
    "text": "Текст",
    "number": "Число",
    "bool": "Да / нет",
    "boolean": "Да / нет",
    "image": "Изображение",
}

#: Настройки, которые читает код площадки (заводит SettingSeeder на
#: каждом деплое; совпадение сверяется тестом). Их не удаляют: так уже
#: пропал фон первого экрана, а с ним и способ сменить картинку
SYSTEM_KEYS: frozenset[str] = frozenset(
    {
        "site_name",
        "site_tagline",
        "support_email",
        "hero_image",
        "support_phone",
        "office_coords",
        "logo_image",
        "support_hours",
        "office_map_zoom",
        "office_address",
        "legal_name",
        "legal_full_name",
        "legal_brand",
        "legal_tin",
        "telegram",
        "legal_address",
        "instagram",
        "legal_actual_address",
        "listing_lifetime_days",
        "legal_phone",
        "moderation_hours",
        "legal_email",
        "reviews_premoderation",
        "legal_bank",
        "legal_mfo",
        "legal_account",
        "legal_director",
        "display_currency_ru",
        "display_currency_uz",
        "display_currency_en",
        "display_currency_zh",
        "display_currency_tr",
    }
)


class LaravelJSONField(models.JSONField):
    """
    Столбец json (не jsonb), как его заводит Laravel.

    Для jsonb Django просит драйвер отдавать текст и разбирает его сам;
    для json драйвер psycopg разбирает значение сам, и Django разбирал
    бы его второй раз — строка «SAVDEX» падала бы как недопустимый JSON.
    Поэтому столбец читается текстом, а разбирает только Django.
    """

    def select_format(self, compiler: Any, sql: str, params: Any) -> Any:  # noqa: ANN401
        if compiler.connection.vendor == "postgresql":
            return f"({sql})::text", params

        return super().select_format(compiler, sql, params)


class RecordIsSystemError(RuntimeError):
    """Настройку читает код площадки — удалять нельзя."""


class Setting(Timestamped):
    group = models.CharField(
        "раздел", max_length=40, choices=list(GROUPS.items()), default="general"
    )
    key = models.CharField("ключ", max_length=190, unique=True)
    label = models.CharField("название", max_length=190)
    description = models.TextField("пояснение", null=True, blank=True)
    type = models.CharField(
        "тип значения", max_length=20, choices=list(TYPES.items()), default="string"
    )
    value = LaravelJSONField("значение", null=True, blank=True)
    sort = models.PositiveSmallIntegerField("порядок", default=0)

    class Meta:
        managed = False
        db_table = "settings"
        ordering = ("group", "sort", "key")
        verbose_name = "настройка"
        verbose_name_plural = "настройки площадки"

    def __str__(self) -> str:
        return self.label if self.pk else "новая настройка"

    @property
    def is_system(self) -> bool:
        return self.key in SYSTEM_KEYS

    @property
    def is_flag(self) -> bool:
        return self.type in ("bool", "boolean")

    def save(self, *args: Any, **kwargs: Any) -> None:
        super().save(*args, **kwargs)
        # static::saved(fn () => self::flushCache())
        laravel_cache.forget(CACHE_KEY)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        if self.is_system:
            raise RecordIsSystemError(
                f"Настройку «{self.key}» читает код площадки — её не удаляют."
            )

        result = super().delete(*args, **kwargs)
        laravel_cache.forget(CACHE_KEY)

        return result
