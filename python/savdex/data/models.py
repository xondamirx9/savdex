"""
Данные площадки глазами админки Django (этап 6). Схема — у Laravel
(managed = False); таблицы этапов 4–5, в них пишет и кабинет, поэтому
запись — в блоке allowed_writes (SHARED_WRITES).

IT-задача (App\\Models\\ItTask):

- ItTask::saving — search_text из заголовка, описания и стека;
- адрес (slug) ставит кабинет при создании; из админки задачи не
  создаются — только правка, снятие и удаление.
"""

from __future__ import annotations

from typing import Any

from django.db import models

from savdex.catalog import LaravelJSONField, Timestamped, UTCDateTimeField
from savdex.crm.models import Company
from savdex.guards import allowed_writes

#: ItTask::STATUSES
IT_STATUSES = {
    "active": "Открыта",
    "closed": "Закрыта",
    "completed": "Выполнена",
    "archived": "В архиве",
}

#: ItTask::SERVICE_TYPES
SERVICE_TYPES = {
    "web": "Сайты и веб-приложения",
    "mobile": "Мобильные приложения",
    "erp": "1С, учёт и ERP",
    "integration": "Интеграции и API",
    "design": "Дизайн и UX",
    "automation": "Автоматизация и боты",
    "support": "Поддержка и администрирование",
    "logistics": "Логистика и перевозки",
    "hr": "Подбор персонала",
    "customs": "Декларирование и ВЭД",
    "accounting": "Бухгалтерские услуги",
    "other": "Другое",
}

BUDGET_TYPES = {"negotiable": "Договорной", "fixed": "Фиксированный", "range": "Диапазон"}

#: ItTask::CURRENCIES
IT_CURRENCIES = ("UZS", "USD")


class ItTask(Timestamped):
    """App\\Models\\ItTask: задача заказчика исполнителям."""

    company = models.ForeignKey(
        Company,
        verbose_name="компания",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="+",
        editable=False,
    )
    user_id = models.BigIntegerField(null=True, editable=False)
    slug = models.CharField(max_length=255, null=True, editable=False)
    title = models.CharField("название", max_length=120)
    description = models.TextField("описание", max_length=8000)
    service_type = models.CharField(
        "вид услуги", max_length=255, choices=list(SERVICE_TYPES.items())
    )
    stack = LaravelJSONField("стек", null=True, blank=True)
    budget_type = models.CharField("бюджет", max_length=255, choices=list(BUDGET_TYPES.items()))
    budget_from = models.DecimalField(
        "от / сумма", max_digits=16, decimal_places=2, null=True, blank=True
    )
    budget_to = models.DecimalField("до", max_digits=16, decimal_places=2, null=True, blank=True)
    currency = models.CharField(
        "валюта", max_length=3, choices=[(c, c) for c in IT_CURRENCIES], default="UZS"
    )
    deadline_at = models.DateField("срок сдачи", null=True, blank=True)
    status = models.CharField("статус", max_length=255, choices=list(IT_STATUSES.items()))
    published_at = UTCDateTimeField("опубликована", null=True, editable=False)
    closed_at = UTCDateTimeField(null=True, editable=False)
    responses_count = models.IntegerField("откликов", default=0, editable=False)
    views_count = models.IntegerField(default=0, editable=False)
    search_text = models.TextField(null=True, editable=False)

    class Meta:
        managed = False
        db_table = "it_tasks"
        # «IT-задача» раздел перерос: сюда попадают логистика,
        # бухгалтерия, декларирование и подбор персонала — всё,
        # что заказывают в «Доп. услугах» на витрине
        verbose_name = "заказ на услугу"
        verbose_name_plural = "заказы на услуги"
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return self.title

    def save(self, *args: Any, **kwargs: Any) -> None:
        """ItTask::saving: search_text заново."""
        from savdex.web.it_task_actions import _search_text

        self.search_text = _search_text(
            {"title": self.title, "description": self.description, "stack": self.stack}
        )["search_text"]

        with allowed_writes("it_tasks"):
            super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        with allowed_writes("it_tasks"):
            return super().delete(*args, **kwargs)


# ── Объявления ───────────────────────────────────────────────────────

LISTING_STATUSES = {
    "draft": "Черновик",
    "moderation": "На проверке",
    "active": "Активно",
    "needs_changes": "На исправлении",
    "rejected": "Отклонено",
    "expired": "Истекло",
    "archived": "Снято",
}

LISTING_TYPES = {"supply": "Предложение", "demand": "Запрос на закупку"}

LISTING_SOURCES = {"cabinet": "Из кабинета", "import": "Загружено из Excel"}

#: Listing::TRANSLATABLE
LISTING_TEXTS = ("title", "description", "delivery_terms", "payment_terms")

#: Listing::MAX_LENGTH
LISTING_MAX = {"title": 90, "description": 5000, "delivery_terms": 2000, "payment_terms": 2000}

#: Listing::LIFETIME_DAYS
LIFETIME_DAYS = 90


class Listing(Timestamped):
    """
    App\\Models\\Listing — для админки: модерация, правка, фотографии.
    Listing::saving — search_text из заголовка, описания и переводов
    заголовка; перевод опубликованного подбирает обработчик Python.
    """

    company = models.ForeignKey(
        Company,
        verbose_name="компания",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        related_name="+",
        editable=False,
    )
    user_id = models.BigIntegerField(null=True, editable=False)
    category_id = models.BigIntegerField("категория", null=True, blank=True)
    city_id = models.BigIntegerField("город", null=True, blank=True)
    type = models.CharField("тип", max_length=255, choices=list(LISTING_TYPES.items()))
    slug = models.CharField(max_length=255, null=True, editable=False)
    title = models.CharField("заголовок", max_length=255)
    description = models.TextField("описание", null=True, blank=True)
    price = models.DecimalField("цена", max_digits=16, decimal_places=2, null=True, blank=True)
    bundle_price = models.DecimalField(
        "цена за весь комплект", max_digits=16, decimal_places=2, null=True, blank=True
    )
    currency = models.CharField("валюта", max_length=255, default="UZS")
    unit = models.CharField("единица", max_length=20, null=True, blank=True)
    price_negotiable = models.BooleanField("цена договорная", default=False)
    min_order = models.IntegerField("минимальный заказ", null=True, blank=True)
    delivery_terms = models.TextField("условия поставки", null=True, blank=True)
    payment_terms = models.TextField("условия оплаты", null=True, blank=True)
    status = models.CharField("статус", max_length=255, editable=False)
    moderation_note = models.TextField("заметка модерации", null=True, blank=True)
    wizard_step = models.SmallIntegerField(default=1, editable=False)
    published_at = UTCDateTimeField(null=True, editable=False)
    expires_at = UTCDateTimeField("действует до", null=True, blank=True)
    impressions_count = models.IntegerField(default=0, editable=False)
    views_count = models.IntegerField("просмотры", default=0, editable=False)
    unlocks_count = models.IntegerField("контакты", default=0, editable=False)
    favorites_count = models.IntegerField(default=0, editable=False)
    deleted_at = UTCDateTimeField(null=True, editable=False)
    search_text = models.TextField(null=True, editable=False)
    tags = LaravelJSONField(null=True, editable=False)
    title_i18n = LaravelJSONField(null=True, editable=False)
    description_i18n = LaravelJSONField(null=True, editable=False)
    delivery_terms_i18n = LaravelJSONField(null=True, editable=False)
    payment_terms_i18n = LaravelJSONField(null=True, editable=False)
    source = models.CharField("источник", max_length=255, default="cabinet", editable=False)

    class Meta:
        managed = False
        db_table = "listings"
        verbose_name = "объявление"
        verbose_name_plural = "объявления"
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return self.title or f"Listing #{self.pk}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Listing::saving: search_text заново."""
        from savdex.web.listing_actions import _search_text

        self.search_text = _search_text(
            {"title": self.title, "description": self.description, "title_i18n": self.title_i18n}
        )

        with allowed_writes("listings"):
            super().save(*args, **kwargs)


class ListingImage(Timestamped):
    """App\\Models\\ListingImage: фото объявления, первое — обложка."""

    listing = models.ForeignKey(
        Listing, on_delete=models.DO_NOTHING, db_constraint=False, related_name="images"
    )
    path = models.CharField(max_length=255)
    thumb_path = models.CharField(max_length=255, null=True)
    sort = models.SmallIntegerField(default=0)

    class Meta:
        managed = False
        db_table = "listing_images"
        ordering = ("sort", "id")

    def __str__(self) -> str:
        return self.path


# ── Компании ─────────────────────────────────────────────────────────

#: CompaniesTable::LEGAL_FORMS
LEGAL_FORMS = {"legal": "Юрлицо", "individual": "Физлицо", "freelancer": "Фрилансер"}

#: CompaniesTable::LEVELS
LEVELS = {0: "Не проверена", 1: "Контакты подтверждены", 2: "Проверена", 3: "Проверена+"}

#: Статусы компании. «Скрыта» — тестовая или пустая карточка убрана с
#: витрины (ТЗ-01, п.4): сайт показывает только active, а вход в кабинет
#: закрывает только blocked
COMPANY_HIDDEN = "hidden"
COMPANY_STATUSES = {
    "active": "Активна",
    "blocked": "Заблокирована",
    COMPANY_HIDDEN: "Скрыта с витрины",
}

#: Company::PARTNER_TIERS
PARTNER_TIERS = {"general": "Генеральный партнёр", "partner": "Партнёр", "multi": "Мультипартнёр"}

#: CompanyForm::ROLES
ROLES = {"supplier": "Поставщик", "buyer": "Закупщик", "both": "И то, и другое"}

#: CompanyForm::EMPLOYEE_RANGES
EMPLOYEE_RANGES = ("1-10", "10-50", "50-100", "100-500", "500+")

#: Company::FALLBACK_TYPES — пока справочник типов пуст
FALLBACK_TYPES = {
    "manufacturer": "Производитель",
    "importer": "Импортёр",
    "distributor": "Дистрибьютор",
    "trader": "Торговая компания",
    "service": "Услуги",
}


class CompanyRecord(Timestamped):
    """
    App\\Models\\Company — карточка для админки. Company::creating — адрес
    из названия; Company::saving — search_text из названия и юр. имени.
    """

    slug = models.CharField(max_length=255, editable=False)
    name = models.CharField("название", max_length=190)
    legal_form = models.CharField(
        "правовая форма",
        max_length=255,
        default="legal",
        choices=list(LEGAL_FORMS.items()),
        help_text="Выбирается при регистрации. У физлица и фрилансера тип бизнеса необязателен.",
    )
    legal_name = models.CharField("юридическое название", max_length=190, null=True, blank=True)
    tin = models.CharField(
        "ИНН", max_length=20, null=True, blank=True, help_text="9 цифр для Узбекистана"
    )
    type = models.CharField(
        "тип",
        max_length=255,
        null=True,
        blank=True,
        help_text="Список правится в справочнике «Типы компаний»",
    )
    primary_role = models.CharField(
        "роль на площадке", max_length=255, default="both", choices=list(ROLES.items())
    )
    founded_year = models.SmallIntegerField("год основания", null=True, blank=True)
    country_id = models.BigIntegerField("страна", null=True, blank=True)
    city_id = models.BigIntegerField("город", null=True, blank=True)
    address = models.CharField("адрес", max_length=255, null=True, blank=True)
    phone = models.CharField("телефон", max_length=32, null=True, blank=True)
    email = models.EmailField("почта", max_length=190, null=True, blank=True)
    website = models.URLField("сайт", max_length=190, null=True, blank=True)
    contact_person = models.CharField("контактное лицо", max_length=120, null=True, blank=True)
    telegram = models.CharField("Telegram", max_length=64, null=True, blank=True)
    whatsapp = models.CharField("WhatsApp", max_length=32, null=True, blank=True)
    description = models.TextField(
        "описание",
        max_length=5000,
        null=True,
        blank=True,
        help_text="Видно на визитке. Профиль с описанием получает заметно больше обращений",
    )
    source_note = models.CharField(
        "пометка об источнике данных",
        max_length=500,
        null=True,
        blank=True,
        help_text="Показывается плашкой на визитке — для карточек, заведённых площадкой из "
        "открытых источников. Пустое поле скрывает плашку.",
    )
    employees_range = models.CharField(
        "сотрудников",
        max_length=255,
        null=True,
        blank=True,
        choices=[(r, r) for r in EMPLOYEE_RANGES],
    )
    response_time_hours = models.SmallIntegerField(
        "отвечает за, часов",
        null=True,
        blank=True,
        help_text="Показывается на визитке как ожидание ответа",
    )
    logo_path = models.CharField(max_length=255, null=True, editable=False)
    cover_path = models.CharField(max_length=255, null=True, editable=False)
    verification_level = models.SmallIntegerField("верификация", default=0, editable=False)
    verified_at = UTCDateTimeField(null=True, editable=False)
    verified_by = models.BigIntegerField(null=True, editable=False)
    rating = models.DecimalField(
        "рейтинг", max_digits=3, decimal_places=2, default=0, editable=False
    )
    reviews_count = models.IntegerField(default=0, editable=False)
    status = models.CharField("статус", max_length=255, default="active", editable=False)
    blocked_reason = models.TextField(null=True, editable=False)
    blocked_at = UTCDateTimeField(null=True, editable=False)
    deleted_at = UTCDateTimeField(null=True, editable=False)
    search_text = models.TextField(null=True, editable=False)
    partner_tier = models.CharField(max_length=255, null=True, editable=False)
    partner_sort = models.IntegerField(default=0, editable=False)

    class Meta:
        managed = False
        db_table = "companies"
        verbose_name = "компания"
        verbose_name_plural = "компании"
        ordering = ("-created_at", "-id")

    def __str__(self) -> str:
        return self.name

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Company::creating — адрес; Company::saving — search_text."""
        from savdex.web.company_profile_actions import _search_text, _slug

        if self._state.adding and not self.slug:
            self.slug = _slug(self.name)

        self.search_text = _search_text({"name": self.name, "legal_name": self.legal_name})[
            "search_text"
        ]

        with allowed_writes("companies"):
            super().save(*args, **kwargs)
