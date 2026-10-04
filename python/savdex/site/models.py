"""
Настройки площадки, баннеры, новости и страницы — перешли к Django
(этап 2).

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

from datetime import datetime
from typing import Any

from django.db import models, transaction
from django.utils import timezone

from savdex import laravel_cache
from savdex.catalog import LOCALES, LaravelJSONField, Timestamped, UTCDateTimeField
from savdex.text import plural

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
    "integrations": "Интеграции",
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
        # Выгрузка «Мебель и всё, что с ней связано» (savdex/data/listing_export.py)
        "furniture_keywords",
        # Ссылка для MEYOS (savdex/data/meyos.py)
        "meyos_feed_enabled",
        "meyos_feed_key",
    }
)


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


# ── Баннеры ─────────────────────────────────────────────────────────

#: Banner::PLACEMENTS
PLACEMENTS: dict[str, str] = {
    "home": "Главная страница",
    "catalog": "Каталог объявлений",
}

#: Banner::DISMISS_DAYS — закрытый баннер не показывается трое суток
DISMISS_DAYS = 3

_MONTHS = (
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
)  # fmt: skip


def _forget_files_later(*paths: str | None) -> None:
    """
    Удалить файлы, когда правка записана.

    Не раньше: сорвись запись после удаления — строка в базе осталась
    бы с путём к файлу, которого уже нет.
    """
    from savdex import images

    wanted = [p for p in paths if p]

    if wanted:
        transaction.on_commit(lambda: images.delete(*wanted))


class Banner(Timestamped):
    """
    Баннер — копия правил App\\Models\\Banner.

    Картинки удаляются с диска вместе с баннером и при замене: диск
    постоянный и небольшой, а снятая акция про свой файл не вспомнит
    никогда. Языковые картинки — тоже.
    """

    name = models.CharField("название для себя", max_length=190)
    placement = models.CharField(
        "место на сайте", max_length=190, choices=list(PLACEMENTS.items()), default="home"
    )
    url = models.CharField("куда ведёт", max_length=500, null=True, blank=True)
    alt = models.CharField("что написано на баннере", max_length=190)
    image_path = models.CharField("картинка для компьютера", max_length=190)
    image_mobile_path = models.CharField(
        "картинка для телефона", max_length=190, null=True, blank=True
    )
    focal_x = models.PositiveSmallIntegerField("точка фокуса по горизонтали, %", default=50)
    focal_y = models.PositiveSmallIntegerField("точка фокуса по вертикали, %", default=50)
    starts_at = UTCDateTimeField("показывать с", null=True, blank=True)
    ends_at = UTCDateTimeField("показывать до", null=True, blank=True)
    is_active = models.BooleanField("включён", default=True)
    is_dismissible = models.BooleanField("можно закрыть крестиком", default=True)
    sort = models.PositiveSmallIntegerField("порядок", default=0)

    class Meta:
        managed = False
        db_table = "banners"
        ordering = ("sort", "-id")
        verbose_name = "баннер"
        verbose_name_plural = "баннеры"

    def __str__(self) -> str:
        return self.name if self.pk else "новый баннер"

    def save(self, *args: Any, **kwargs: Any) -> None:
        old = (
            Banner.objects.filter(pk=self.pk).values("image_path", "image_mobile_path").first()
            if self.pk
            else None
        )
        super().save(*args, **kwargs)

        if old:
            _forget_files_later(
                *(old[c] for c in ("image_path", "image_mobile_path") if old[c] != getattr(self, c))
            )

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        # Строки языковых картинок уносит каскад, их события не
        # срабатывают — файлы собираются здесь, до удаления
        paths = [self.image_path, self.image_mobile_path]

        for image in self.images.all():
            paths += [image.image_path, image.image_mobile_path]

        result = super().delete(*args, **kwargs)
        _forget_files_later(*paths)

        return result

    def is_live(self, now: datetime | None = None) -> bool:
        """Banner::isLive(): идёт ли прямо сейчас."""
        now = now or timezone.now()

        return (
            self.is_active
            and (self.starts_at is None or self.starts_at <= now)
            and (self.ends_at is None or self.ends_at > now)
        )

    def countdown(self, now: datetime | None = None) -> str:
        """Banner::countdown(): «осталось 2 дня» говорит больше, чем «до 30 октября»."""
        now = now or timezone.now()

        if self.ends_at is None:
            return "бессрочно"

        if self.ends_at <= now:
            return "закончилась"

        if self.starts_at is not None and self.starts_at > now:
            local = timezone.localtime(self.starts_at)

            return f"старт {local.day:02d} {_MONTHS[local.month - 1]}"

        seconds = (self.ends_at - now).total_seconds()
        days = int(seconds // 86400)

        if days >= 1:
            return f"осталось {plural(days, 'день', 'дня', 'дней')}"

        hours = int(seconds // 3600)

        return f"осталось {plural(hours, 'час', 'часа', 'часов')}" if hours >= 1 else "меньше часа"


class BannerImage(Timestamped):
    """Картинка баннера под отдельный язык — App\\Models\\BannerImage."""

    banner = models.ForeignKey(
        Banner, on_delete=models.CASCADE, related_name="images", db_column="banner_id"
    )
    locale = models.CharField("язык", max_length=5, choices=list(LOCALES.items()))
    image_path = models.CharField("для компьютера", max_length=190)
    image_mobile_path = models.CharField("для телефона", max_length=190, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "banner_images"
        unique_together = (("banner", "locale"),)
        verbose_name = "картинка под язык"
        verbose_name_plural = "картинки под отдельные языки"

    def __str__(self) -> str:
        return LOCALES.get(self.locale, self.locale)

    def save(self, *args: Any, **kwargs: Any) -> None:
        old = (
            BannerImage.objects.filter(pk=self.pk).values("image_path", "image_mobile_path").first()
            if self.pk
            else None
        )
        super().save(*args, **kwargs)

        if old:
            _forget_files_later(
                *(old[c] for c in ("image_path", "image_mobile_path") if old[c] != getattr(self, c))
            )

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        paths = (self.image_path, self.image_mobile_path)
        result = super().delete(*args, **kwargs)
        _forget_files_later(*paths)

        return result


# ── Новости ─────────────────────────────────────────────────────────

#: NewsPost::CATEGORIES — рубрики задают оформление обложки
NEWS_CATEGORIES: tuple[str, ...] = (
    "Обновления сервиса",
    "Тарифы и оплата",
    "Аналитика рынка",
    "Полезное",
)

#: Текст и его машинный перевод: правка текста делает перевод неверным
_TRANSLATED = {"title": "title_i18n", "excerpt": "excerpt_i18n", "body": "body_i18n"}


class NewsPost(Timestamped):
    """
    Новость — копия правил App\\Models\\NewsPost.

    У таблицы два писателя, по столбцам: текст правит Django, а
    машинный перевод (*_i18n) пишет задача Laravel TranslateNewsPost —
    только эти столбцы и только их. Поэтому:

    - Django не пишет столбцы перевода при обычном сохранении, чтобы
      не затереть перевод, который задача успела записать, пока форма
      была открыта;
    - правка заголовка, описания или текста сбрасывает перевод этого
      поля. Laravel переводил новость один раз и больше на текст не
      смотрел: исправленная новость навсегда оставалась на других
      языках со старым переводом. Сброшенный перевод подбирает задача
      news-translate-catchup (routes/console.php) в течение пяти минут.
    """

    slug = models.CharField("адрес", max_length=190, unique=True)
    category = models.CharField("рубрика", max_length=190)
    title = models.CharField("заголовок", max_length=190)
    title_i18n = LaravelJSONField(null=True, blank=True, editable=False)
    excerpt = models.TextField("краткое описание")
    excerpt_i18n = LaravelJSONField(null=True, blank=True, editable=False)
    body = models.TextField("текст")
    body_i18n = LaravelJSONField(null=True, blank=True, editable=False)
    image_path = models.CharField("обложка", max_length=190, null=True, blank=True)
    read_time = models.CharField("время чтения", max_length=20, null=True, blank=True)
    is_published = models.BooleanField("опубликована", default=False)
    published_at = UTCDateTimeField("дата публикации", null=True, blank=True)
    sort = models.PositiveSmallIntegerField("порядок", default=0)
    # Ссылка на users без модели: таблица пользователей — Laravel
    author_id = models.BigIntegerField(null=True, blank=True, editable=False)

    class Meta:
        managed = False
        db_table = "news_posts"
        ordering = ("-published_at", "-sort", "-id")
        verbose_name = "новость"
        verbose_name_plural = "новости"

    def __str__(self) -> str:
        return self.title if self.pk else "новая новость"

    def status(self, now: datetime | None = None) -> str:
        """Три состояния, а не два: «опубликована» и «выйдет 5 августа» — разное."""
        if not self.is_published:
            return "draft"

        if self.published_at is not None and self.published_at > (now or timezone.now()):
            return "scheduled"

        return "published"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self._state.adding or kwargs.get("update_fields") is not None:
            super().save(*args, **kwargs)
            return

        old = NewsPost.objects.filter(pk=self.pk).values(*_TRANSLATED, "image_path").first() or {}
        changed = [
            i18n for text, i18n in _TRANSLATED.items() if old.get(text) != getattr(self, text)
        ]

        for i18n in changed:
            setattr(self, i18n, None)

        own = [
            f.attname
            for f in self._meta.concrete_fields
            if not f.primary_key and f.attname not in _TRANSLATED.values()
        ]
        super().save(*args, update_fields=[*own, *changed], **kwargs)

        # Заменённая или снятая обложка — с диска, после записи
        if old.get("image_path") and old["image_path"] != self.image_path:
            _forget_files_later(old["image_path"])

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        cover = self.image_path
        result = super().delete(*args, **kwargs)
        _forget_files_later(cover)

        return result


# ── Страницы и вопросы помощи ───────────────────────────────────────

#: Page::KEYS — набор страниц задан кодом: у каждой свой адрес и своя
#: вёрстка, админка правит только текст
PAGE_ADDRESSES: dict[str, str] = {
    "about": "/about",
    "contacts": "/about#contacts",
    "help": "/help",
    "guide": "/guide",
    "rules": "/rules",
}

#: Page::DOCS — страницы со своим адресом: их можно скрыть
PAGE_DOCS: frozenset[str] = frozenset({"help", "guide", "rules"})


class Page(Timestamped):
    """
    Страница о площадке — копия правил App\\Models\\Page.

    Русский текст — в основных столбцах, остальные языки — в *_i18n
    ({"uz": "...", "en": "..."}), и их пишет администратор (в отличие
    от новостей, где *_i18n — машинный перевод). Незаполненный язык
    сайт показывает машинным переводом русского текста.

    Страницы не заводятся и не удаляются: их набор задан кодом сайта.
    """

    key = models.CharField("ключ", max_length=190, unique=True, editable=False)
    slug = models.CharField("адрес", max_length=190, unique=True, editable=False)
    title = models.CharField("заголовок", max_length=190)
    title_i18n = LaravelJSONField(null=True, blank=True, editable=False)
    excerpt = models.TextField("подзаголовок", null=True, blank=True)
    excerpt_i18n = LaravelJSONField(null=True, blank=True, editable=False)
    body = models.TextField("текст", null=True, blank=True)
    body_i18n = LaravelJSONField(null=True, blank=True, editable=False)
    meta_title = models.CharField("заголовок в поиске", max_length=190, null=True, blank=True)
    meta_description = models.CharField("описание в поиске", max_length=255, null=True, blank=True)
    is_published = models.BooleanField("опубликована", default=True)
    sort = models.PositiveSmallIntegerField("порядок", default=0)

    class Meta:
        managed = False
        db_table = "pages"
        ordering = ("sort", "id")
        verbose_name = "страница"
        verbose_name_plural = "страницы и FAQ"

    def __str__(self) -> str:
        return self.title

    @property
    def address(self) -> str:
        return PAGE_ADDRESSES.get(self.key, f"/{self.slug}")

    @property
    def can_hide(self) -> bool:
        """«О компании» и «Контакты» скрыть нельзя: это одна страница /about."""
        return self.key in PAGE_DOCS


class FaqItem(Timestamped):
    """Вопрос-ответ на странице «Помощь» — языки как у Page."""

    page = models.ForeignKey(
        Page, on_delete=models.CASCADE, related_name="faq_items", null=True, db_column="page_id"
    )
    question = models.CharField("вопрос", max_length=190)
    question_i18n = LaravelJSONField(null=True, blank=True, editable=False)
    answer = models.TextField("ответ")
    answer_i18n = LaravelJSONField(null=True, blank=True, editable=False)
    sort = models.PositiveSmallIntegerField("порядок", default=0)
    is_published = models.BooleanField("показывать", default=True)

    class Meta:
        managed = False
        db_table = "faq_items"
        ordering = ("sort", "id")
        verbose_name = "вопрос"
        verbose_name_plural = "Вопросы и ответы"

    def __str__(self) -> str:
        return self.question


# ── Главная страница ────────────────────────────────────────────────

#: LandingBlock::KEYS — секции главной в порядке макета
LANDING_KEYS: tuple[str, ...] = (
    "hero",
    "stats",
    "categories",
    "vip",
    "products",
    "requests",
    "suppliers",
    "how",
    "reviews",
    "faq",
    "news",
    "cta",
)


class LandingBlock(Timestamped):
    """
    Секция главной — копия правил App\\Models\\LandingBlock.

    Правятся тексты и видимость; порядок задан макетом, секции не
    заводятся и не удаляются. Языки — как у Page: русский в основных
    столбцах, остальные — в *_i18n, пустой язык сайт переводит машиной.
    У «Как это работает» и «Частых вопросов» пункты — в body: название
    первой строкой, пояснение следующей, пункты через пустую строку.
    """

    key = models.CharField("ключ", max_length=190, unique=True, editable=False)
    name = models.CharField("секция", max_length=190, editable=False)
    eyebrow = models.CharField("надзаголовок", max_length=190, null=True, blank=True)
    eyebrow_i18n = LaravelJSONField(null=True, blank=True, editable=False)
    heading = models.CharField("заголовок", max_length=190, null=True, blank=True)
    heading_i18n = LaravelJSONField(null=True, blank=True, editable=False)
    subheading = models.TextField("подзаголовок", null=True, blank=True)
    subheading_i18n = LaravelJSONField(null=True, blank=True, editable=False)
    button = models.CharField("кнопка", max_length=190, null=True, blank=True)
    button_i18n = LaravelJSONField(null=True, blank=True, editable=False)
    body = models.TextField("текст", null=True, blank=True)
    body_i18n = LaravelJSONField(null=True, blank=True, editable=False)
    # Прежнее поле Filament: сайт его не читает, Django не трогает
    payload = LaravelJSONField(null=True, blank=True, editable=False)
    is_visible = models.BooleanField("показывать", default=True)
    sort = models.PositiveSmallIntegerField("порядок", default=0, editable=False)

    class Meta:
        managed = False
        db_table = "landing_blocks"
        ordering = ("sort", "id")
        verbose_name = "секция главной"
        verbose_name_plural = "главная страница"

    def __str__(self) -> str:
        return self.name

    @property
    def can_hide(self) -> bool:
        """Первый экран не скрывается: на нём поиск."""
        return self.key != "hero"
