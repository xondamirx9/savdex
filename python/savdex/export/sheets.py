"""
Листы выгрузки: что берётся из какой таблицы и как называется.

Перенесено из App\\Console\\Commands\\ExportWorkbooks (методы
companySheets и listingSheets) — сгенерировано из PHP-исходника,
а не перепечатано: 235 столбцов руками без опечатки не переносятся.

Пока обе половины живут рядом, описание обязано совпадать с PHP-версией
столбец в столбец — это держит tests/test_export_sheets.py. Правите
здесь — правьте и там.

Столбец — тройка (заголовок, поле, тип). Поле с «@» — вычисляемое:
читаемое название вместо идентификатора или счётчик (см. workbooks.py).
Типы: int, float, bool, date, datetime, text.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Sheet:
    name: str
    table: str
    about: str
    columns: tuple[tuple[str, str, str], ...]


COMPANY_SHEETS: tuple[Sheet, ...] = (
    Sheet(
        name="Компании",
        table="companies",
        about=("Карточки компаний, включая удалённые. Главный лист книги."),
        columns=(
            ("ID", "id", "int"),
            ("Адрес страницы", "slug", "text"),
            ("Название", "name", "text"),
            ("Юридическое название", "legal_name", "text"),
            ("ИНН / СТИР", "tin", "text"),
            ("Страна", "@country", "text"),
            ("ID страны", "country_id", "int"),
            ("Город", "@city", "text"),
            ("ID города", "city_id", "int"),
            ("Адрес", "address", "text"),
            ("Широта", "lat", "float"),
            ("Долгота", "lng", "float"),
            ("Тип", "type", "text"),
            ("Роль", "primary_role", "text"),
            ("Описание", "description", "text"),
            ("Сайт", "website", "text"),
            ("Телефон", "phone", "text"),
            ("Email", "email", "text"),
            ("Telegram", "telegram", "text"),
            ("WhatsApp", "whatsapp", "text"),
            ("Контактное лицо", "contact_person", "text"),
            ("Год основания", "founded_year", "int"),
            ("Размер штата", "employees_range", "text"),
            ("Оборот", "turnover_range", "text"),
            ("Уровень проверки", "verification_level", "int"),
            ("Проверена", "verified_at", "datetime"),
            ("Кем проверена", "@verified_by", "text"),
            ("Рейтинг", "rating", "float"),
            ("Отзывов", "reviews_count", "int"),
            ("Сделок", "completed_deals_count", "int"),
            ("Ответ, часов", "response_time_hours", "int"),
            ("Статус", "status", "text"),
            ("Причина блокировки", "blocked_reason", "text"),
            ("Заблокирована", "blocked_at", "datetime"),
            ("Учётных записей", "@users_count", "int"),
            ("Объявлений всего", "@listings_total", "int"),
            ("Из них активных", "@listings_active", "int"),
            ("Раскрытий контактов", "@unlocks_made", "int"),
            ("Своя категория", "custom_category", "text"),
            ("Пометка источника", "source_note", "text"),
            ("Логотип", "logo_path", "text"),
            ("Обложка", "cover_path", "text"),
            ("Создана", "created_at", "datetime"),
            ("Обновлена", "updated_at", "datetime"),
            ("Удалена", "deleted_at", "datetime"),
        ),
    ),
    Sheet(
        name="Сотрудники",
        table="users",
        about=(
            "Учётные записи людей. Здесь видно тестовые регистрации: почта, дата создания, подтверждён ли адрес, был ли вход."
        ),
        columns=(
            ("ID", "id", "int"),
            ("Имя", "name", "text"),
            ("Email", "email", "text"),
            ("Email подтверждён", "email_verified_at", "datetime"),
            ("Телефон", "phone", "text"),
            ("Телефон подтверждён", "phone_verified_at", "datetime"),
            ("ID компании", "company_id", "int"),
            ("Компания", "@company", "text"),
            ("Роль в компании", "company_role", "text"),
            ("Администратор площадки", "is_admin", "bool"),
            ("Роль администратора", "admin_role", "text"),
            ("Язык", "locale", "text"),
            ("Статус", "status", "text"),
            ("Последний вход", "last_login_at", "datetime"),
            ("IP последнего входа", "last_login_ip", "text"),
            ("Создан", "created_at", "datetime"),
            ("Обновлён", "updated_at", "datetime"),
            ("Удалён", "deleted_at", "datetime"),
        ),
    ),
    Sheet(
        name="Контакты",
        table="company_contacts",
        about=("Дополнительные контакты компаний сверх тех, что лежат в карточке."),
        columns=(
            ("ID", "id", "int"),
            ("ID компании", "company_id", "int"),
            ("Компания", "@company", "text"),
            ("Вид", "type", "text"),
            ("Значение", "value", "text"),
            ("Подпись", "label", "text"),
            ("Контактное лицо", "contact_person", "text"),
            ("Основной", "is_primary", "bool"),
            ("Публичный", "is_public", "bool"),
            ("Порядок", "sort_order", "int"),
            ("Создан", "created_at", "datetime"),
        ),
    ),
    Sheet(
        name="Категории компаний",
        table="company_category",
        about=("Какая компания в каких разделах каталога. Одна строка — одна связь."),
        columns=(
            ("ID", "id", "int"),
            ("ID компании", "company_id", "int"),
            ("Компания", "@company", "text"),
            ("ID категории", "category_id", "int"),
            ("Категория", "@category", "text"),
            ("Создана", "created_at", "datetime"),
        ),
    ),
    Sheet(
        name="Документы",
        table="company_documents",
        about=(
            "Загруженные компаниями документы. Сами файлы лежат на диске, здесь только их описания и пути."
        ),
        columns=(
            ("ID", "id", "int"),
            ("ID компании", "company_id", "int"),
            ("Компания", "@company", "text"),
            ("Вид", "type", "text"),
            ("Название", "title", "text"),
            ("Путь к файлу", "file_path", "text"),
            ("Размер, байт", "file_size", "int"),
            ("Тип файла", "mime", "text"),
            ("Действует до", "valid_until", "date"),
            ("Публичный", "is_public", "bool"),
            ("Модерация", "moderation_status", "text"),
            ("Замечание модератора", "moderation_note", "text"),
            ("Создан", "created_at", "datetime"),
        ),
    ),
    Sheet(
        name="Кошельки",
        table="wallets",
        about=(
            "Остатки кредитов на раскрытие контактов и единиц продвижения. Один кошелёк на компанию."
        ),
        columns=(
            ("ID", "id", "int"),
            ("ID компании", "company_id", "int"),
            ("Компания", "@company", "text"),
            ("Кредиты", "credits", "int"),
            ("Единицы продвижения", "promo_units", "int"),
            ("Контактов за период", "contacts_used_this_period", "int"),
            ("Откликов за период", "responses_used_this_period", "int"),
            ("Период сбросится", "period_resets_at", "datetime"),
            ("Создан", "created_at", "datetime"),
        ),
    ),
    Sheet(
        name="Подписки",
        table="subscriptions",
        about=("Кто на каком тарифе и до какого числа."),
        columns=(
            ("ID", "id", "int"),
            ("ID компании", "company_id", "int"),
            ("Компания", "@company", "text"),
            ("ID тарифа", "plan_id", "int"),
            ("Тариф", "@plan", "text"),
            ("Статус", "status", "text"),
            ("Начало", "started_at", "datetime"),
            ("Окончание", "ends_at", "datetime"),
            ("Автопродление", "auto_renew", "bool"),
            ("Отменена", "cancelled_at", "datetime"),
            ("Источник", "source", "text"),
            ("Основание выдачи", "grant_reason", "text"),
            ("Создана", "created_at", "datetime"),
        ),
    ),
    Sheet(
        name="Доп. поля компаний",
        table="company_attributes",
        about=("Произвольные поля, которые администратор добавляет компаниям без правки схемы."),
        columns=(
            ("ID", "id", "int"),
            ("ID компании", "company_id", "int"),
            ("Компания", "@company", "text"),
            ("Поле", "key", "text"),
            ("Значение", "value", "text"),
            ("Тип", "type", "text"),
            ("Создано", "created_at", "datetime"),
        ),
    ),
    Sheet(
        name="Раскрытые контакты",
        table="contact_unlocks",
        about=(
            "Кто чьи контакты открыл. Самый honest признак живой компании: за раскрытие платят."
        ),
        columns=(
            ("ID", "id", "int"),
            ("ID открывшего", "company_id", "int"),
            ("Кто открыл", "@company", "text"),
            ("ID чьи контакты", "target_company_id", "int"),
            ("Чьи контакты", "@target_company", "text"),
            ("ID объявления", "listing_id", "int"),
            ("Списано кредитов", "credits_spent", "int"),
            ("Статус работы", "status", "text"),
            ("Заметка", "note", "text"),
            ("Жалоба", "complaint_status", "text"),
            ("Причина жалобы", "complaint_reason", "text"),
            ("Кредит возвращён", "refunded", "bool"),
            ("Создано", "created_at", "datetime"),
        ),
    ),
    Sheet(
        name="Отзывы",
        table="reviews",
        about=("Отзывы компаний друг о друге с оценками по составляющим."),
        columns=(
            ("ID", "id", "int"),
            ("ID компании", "company_id", "int"),
            ("О ком отзыв", "@company", "text"),
            ("ID автора", "author_company_id", "int"),
            ("Автор", "@author_company", "text"),
            ("ID объявления", "listing_id", "int"),
            ("Оценка", "rating", "int"),
            ("Описание товара", "rating_description", "int"),
            ("Ответы", "rating_response", "int"),
            ("Сроки", "rating_deadlines", "int"),
            ("Качество", "rating_quality", "int"),
            ("Текст", "body", "text"),
            ("Сделка подтверждена", "deal_confirmed", "bool"),
            ("Ответ компании", "reply", "text"),
            ("Статус", "status", "text"),
            ("Спор", "dispute_status", "text"),
            ("Создан", "created_at", "datetime"),
        ),
    ),
)

LISTING_SHEETS: tuple[Sheet, ...] = (
    Sheet(
        name="Объявления",
        table="listings",
        about=("Объявления площадки, включая черновики и удалённые. Главный лист книги."),
        columns=(
            ("ID", "id", "int"),
            ("ID компании", "company_id", "int"),
            ("Компания", "@company", "text"),
            ("ID автора", "user_id", "int"),
            ("Автор", "@user", "text"),
            ("Вид", "type", "text"),
            ("Адрес страницы", "slug", "text"),
            ("Заголовок", "title", "text"),
            ("Описание", "description", "text"),
            ("ID категории", "category_id", "int"),
            ("Категория", "@category", "text"),
            ("ID города", "city_id", "int"),
            ("Город", "@city", "text"),
            ("Цена", "price", "float"),
            ("Цена за партию", "bundle_price", "float"),
            ("Валюта", "currency", "text"),
            ("Единица", "unit", "text"),
            ("Цена договорная", "price_negotiable", "bool"),
            ("Минимальный заказ", "min_order", "int"),
            ("Условия доставки", "delivery_terms", "text"),
            ("Условия оплаты", "payment_terms", "text"),
            ("Метки", "tags", "text"),
            ("Статус", "status", "text"),
            ("Замечание модератора", "moderation_note", "text"),
            ("Шаг мастера", "wizard_step", "int"),
            ("Опубликовано", "published_at", "datetime"),
            ("Истекает", "expires_at", "datetime"),
            ("Показов", "impressions_count", "int"),
            ("Просмотров", "views_count", "int"),
            ("Раскрытий контакта", "unlocks_count", "int"),
            ("В избранном", "favorites_count", "int"),
            ("Переводы заголовка", "title_i18n", "text"),
            ("Создано", "created_at", "datetime"),
            ("Обновлено", "updated_at", "datetime"),
            ("Удалено", "deleted_at", "datetime"),
        ),
    ),
    Sheet(
        name="Фотографии",
        table="listing_images",
        about=(
            "Фотографии объявлений. Сами файлы лежат на диске, здесь пути к ним и порядок показа."
        ),
        columns=(
            ("ID", "id", "int"),
            ("ID объявления", "listing_id", "int"),
            ("Объявление", "@listing", "text"),
            ("Путь к файлу", "path", "text"),
            ("Путь к миниатюре", "thumb_path", "text"),
            ("Порядок", "sort", "int"),
            ("Создана", "created_at", "datetime"),
        ),
    ),
    Sheet(
        name="Характеристики",
        table="listing_attributes",
        about=("Поля объявления, зависящие от категории: марка, сорт, размер и прочее."),
        columns=(
            ("ID", "id", "int"),
            ("ID объявления", "listing_id", "int"),
            ("Объявление", "@listing", "text"),
            ("Поле", "key", "text"),
            ("Значение", "value", "text"),
            ("Создано", "created_at", "datetime"),
        ),
    ),
    Sheet(
        name="Статистика по дням",
        table="listing_stats",
        about=("По одной строке на объявление и день. Отсюда строятся графики в кабинете."),
        columns=(
            ("ID", "id", "int"),
            ("ID объявления", "listing_id", "int"),
            ("Объявление", "@listing", "text"),
            ("Дата", "date", "date"),
            ("Показов", "impressions", "int"),
            ("Просмотров", "views", "int"),
            ("В избранное", "favorites", "int"),
            ("Раскрытий", "unlocks", "int"),
        ),
    ),
    Sheet(
        name="Избранное",
        table="favorites",
        about=(
            "Кто какие объявления сохранил. Шаг воронки между просмотром и раскрытием контакта."
        ),
        columns=(
            ("ID", "id", "int"),
            ("ID пользователя", "user_id", "int"),
            ("Пользователь", "@user", "text"),
            ("ID объявления", "listing_id", "int"),
            ("Объявление", "@listing", "text"),
            ("Добавлено", "created_at", "datetime"),
        ),
    ),
    Sheet(
        name="Тендеры",
        table="tenders",
        about=(
            "Закупки, заведённые отдельно от объявлений: со своим заказчиком, бюджетом и сроком подачи."
        ),
        columns=(
            ("ID", "id", "int"),
            ("Адрес страницы", "slug", "text"),
            ("Заголовок", "title", "text"),
            ("Описание", "description", "text"),
            ("Заказчик", "customer", "text"),
            ("ID категории", "category_id", "int"),
            ("Категория", "@category", "text"),
            ("ID страны", "country_id", "int"),
            ("Страна", "@country", "text"),
            ("Место", "location", "text"),
            ("Бюджет", "budget", "float"),
            ("Валюта", "currency", "text"),
            ("Приём до", "deadline_at", "datetime"),
            ("Источник", "source_url", "text"),
            ("Контактное лицо", "contact_name", "text"),
            ("Телефон", "contact_phone", "text"),
            ("Email", "contact_email", "text"),
            ("Статус", "status", "text"),
            ("Опубликован", "published_at", "datetime"),
            ("Просмотров", "views_count", "int"),
            ("Создан", "created_at", "datetime"),
        ),
    ),
)
