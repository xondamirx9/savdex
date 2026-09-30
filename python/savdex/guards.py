"""
Предохранители переноса.

Здесь в коде закреплены правила 4.1 и 4.2 из
`docs/migration-to-python.md`: у каждой таблицы один хозяин на запись,
и миграции запускает только Laravel.

Договорённость, которую держит только совесть, не держится. За полтора
года переноса кто-нибудь напишет `Company.objects.filter(...).update(...)`
в таблицу, которая всё ещё принадлежит Laravel, — и обойдёт правила,
живущие в событиях моделей Eloquent (раздел 5 того же документа):
пересчёт рейтинга, запрет возвращать отклонённое объявление на витрину,
сброс устаревших переводов. Ошибка не проявится сразу и не проявится
громко; она проявится расхождением данных через месяц.

Поэтому запись запрещена по умолчанию и разрешается таблице поимённо.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any

from django.db.backends.signals import connection_created
from django.dispatch import receiver

if TYPE_CHECKING:
    from collections.abc import Callable

    from django.db.backends.base.base import BaseDatabaseWrapper

# ── Кому уже разрешено писать ───────────────────────────────────────

#: Таблицы, чей хозяин — Django.
#:
#: На этапах 0 и 1 был пуст: Django только читал.
#:
#: Добавление строки сюда — и есть «переход хозяина» из плана переноса.
#: Прежде чем добавить, нужно выполнить три условия:
#:
#: 1. Правила модели из раздела 5 документа перенесены;
#: 2. На них написаны тесты pytest, и они падают без переноса;
#: 3. Laravel в эту таблицу больше не пишет.
#:
#: Порядок перехода — раздел 6 документа.
OWNED_TABLES: frozenset[str] = frozenset(
    {
        # Этап 2: справочник стран. Правила Country перенесены
        # (savdex/geo/models.py), раздел в Filament убран, GeoSeeder
        # существующие страны больше не перезаписывает
        "countries",
        "country_translations",
        # Этап 2: города — то же для City и GeoSeeder (города он тоже
        # больше не перезаписывает)
        "cities",
        "city_translations",
        # Этап 2: типы компаний. Запрет удаления используемого типа
        # перенесён из кнопки Filament в модель (обе половины)
        "company_types",
        "company_type_translations",
        # Этап 2: категории. Запрет удаления при ссылках появился в
        # обеих половинах, CategorySeeder существующие не перезаписывает.
        # Поля категорий (category_fields) остаются за Laravel: их правит
        # только сидер
        "categories",
        "category_translations",
        # Этап 2: пакеты контактов. Запрет удаления пакета со счетами
        # (в Filament его не было, хотя комментарий обещал)
        "credit_packs",
        # Этап 2: настройки площадки. После правки Django сам сбрасывает
        # кэш настроек Laravel (savdex/laravel_cache.py); настройки,
        # которые читает код, не удаляются
        "settings",
        # Этап 2: баннеры. Картинки пересобираются как ImageStore
        # (savdex/images.py), прежние файлы удаляются после записи
        "banners",
        "banner_images",
        # Этап 2: новости. Два писателя по столбцам: текст — Django,
        # машинный перевод (*_i18n) — задача Laravel TranslateNewsPost,
        # только эти столбцы. Django их не пишет, кроме сброса перевода
        # изменённого поля (savdex/site/models.py, NewsPost)
        "news_posts",
        # Этап 2: тарифы. Цены и лимиты задаёт админка (решение
        # заказчика): PlanSeeder на деплое только досоздаёт недостающие
        "plans",
        # Этап 2: страницы и вопросы помощи. Сайт теперь читает их
        # (раньше — словарь); языки — свои поля в *_i18n, их пишет
        # администратор, пустые сайт переводит машиной
        "pages",
        "faq_items",
        # Этап 2: главная страница. Правятся тексты, вопросы и видимость
        # секций, порядок — как в макете; языки — как у страниц
        "landing_blocks",
        # Этап 6: контакты CRM. Кроме раздела админки в таблицу никто не
        # пишет; SoftDeletes и «кто завёл» — в savdex/crm, раздел Filament
        # убран
        "crm_contacts",
        # Этап 6: лиды и сделки — вместе («В сделку» пишет в обе). Правило
        # Deal::saving (дата закрытия) — в savdex/crm/models.py, разделы
        # Filament убраны, виджет «Лиды в работе» только читает
        "crm_leads",
        "crm_deals",
        # Этап 6: задачи и коммуникации. Разделы Filament убраны, виджет
        # «Задачи на сегодня» и счётчик просроченных у пункта меню только
        # читают; запись разговора удаляется насовсем (DELETE)
        "crm_tasks",
        "crm_communications",
        # Этап 6: обращения в поддержку. Кроме раздела админки пишет только
        # обращение владельца о смене данных компании (этап 5, шаг 51,
        # web/company_info_actions.py); Ticket::saving (дата закрытия) — в
        # savdex/support/models.py. Раздел Filament убран, виджет «Открытые
        # обращения» и счётчик у пункта меню только читают
        "support_tickets",
        "support_messages",
        # Этап 4 (шаг 62): каталог. Все формы и страницы — на Django (группы
        # catalog, tenders, services, cabinet, forms); снятие истёкших
        # объявлений — manage.py expire_listings вместо listings:expire.
        # У Laravel остались писатели только на аварийный откат
        # (SAVDEX_PY_PAGES без forms, SAVDEX_PY_TRANSLATE=0) и демо-стенд
        # (SEED_DEMO, SEED_SHOWCASE) — docs/migration-to-python.md, шаг 62
        "listings",
        "listing_attributes",
        "listing_images",
        "listing_stats",
        "favorites",
        "search_hits",
        "tenders",
        "it_tasks",
        "it_task_files",
        "resumes",
        # Этап 5 (шаг 63): кабинет, кроме users, companies и
        # user_notifications (у тех ещё есть живые писатели Laravel — шаги
        # 64–66). Все формы — на Django; чистка «Кто смотрел» —
        # savdex/schedule.py вместо audience-views:prune. Остальное у
        # Laravel — только аварийный откат и демо-стенд, как на шаге 62
        "login_attempts",
        "company_attributes",
        "company_category",
        "company_contacts",
        "company_documents",
        "company_invitations",
        "company_sites",
        "company_site_products",
        "reviews",
        "platform_reviews",
        "contact_unlocks",
        "audience_views",
        "message_threads",
        "messages",
        "notifications",
        "notification_preferences",
        "broadcasts",
        # Этап 5 (шаг 64): компании. Последний живой писатель Laravel —
        # пересчёт рейтингов ratings:recalculate — перенесён в
        # savdex/schedule.py; событие saving (search_text) у Django своё
        "companies",
        # Этап 5 (шаг 65): колокольчик. Просьбы об отзыве (reviews:ask) —
        # savdex/schedule.py; с шага 72 и денежные уведомления (продление,
        # конец подписки) — savdex/payments/periods.py
        "user_notifications",
        # Шаг 70: пользователи. Последние живые писатели Laravel — смена
        # языка ?hl= (SetLocale) и регистрация по коду — на Django
        # (web/request.py, web/register_code.py). Сброс пароля — формы Django
        "users",
        "password_reset_tokens",
        # Шаг 72: деньги — по решению владельца раньше конца месяца сверки
        # (docs/migration-to-python.md). promotions:finish и
        # billing:reset-periods — savdex/payments/periods.py; касса, шлюз
        # Uzum, возвраты и разделы денег в админке — Django с этапа 7.
        # Сверка денег (manage.py reconcile_billing) продолжает работать
        "wallets",
        "wallet_transactions",
        "promotions",
        "subscriptions",
        "payment_methods",
        "payments",
        "payment_transactions",
        "promo_codes",
        "refunds",
        # Шаг 73: справочники деплоя (manage.py seed вместо сидеров
        # Laravel). Поля категорий и типы продвижения писали только сидеры
        "category_fields",
        "promotion_types",
    }
)

#: Журнал действий — единственное исключение (раздел 5.1 документа).
#:
#: В него пишут обе стороны с этапа 2, и это безопасно: таблица
#: добавляемая, а изменение и удаление запрещены самой моделью.
#: Делить двум писателям нечего.
APPEND_ONLY_SHARED: frozenset[str] = frozenset({"admin_actions"})


#: Чужие таблицы, в которые Django может писать — но только внутри
#: `allowed_writes(...)`, то есть в том месте кода, которое это заявило.
#:
#: Это не переход хозяина: Laravel продолжает писать в таблицу, и
#: правила её модели по-прежнему его. Годится только для таблиц без
#: событий модели (раздел 5 документа) и для записи, которую Laravel
#: делает тем же простым путём. Против каждой — кто пишет и почему
#: это безопасно.
SHARED_WRITES: dict[str, str] = {
    "sessions": (
        "сессия Laravel на страницах сайта (этап 5): Django ведёт её, как "
        "StartSession и DatabaseSessionHandler, — продлевает, стирает "
        "одноразовые сообщения, заводит сессию гостю, запоминает адрес и "
        "язык; вход по «запомнить меня» переносит сессию на новый номер"
    ),
    "content_translations": (
        "очередь машинного перевода (этап 3): страница на Django, как и "
        "ContentTranslation у Laravel, ставит непереведённый текст в очередь "
        "— только insert … on conflict do nothing; переводит задача Laravel "
        "translations:fill"
        "; машинный перевод (этап 5, manage.py translate) — перевод и число "
        "попыток, как translations:fill"
    ),
    "activity_events": (
        "лента кабинета (этап 5, форма): insert события, как Notifier::company "
        "при повторной публикации объявления; событий у модели нет"
        "; решения по отзывам в админке (этап 6) — то же событие компании"
    ),
    "cache": (
        "сброс кэша Laravel после правки из Django (savdex/laravel_cache.py): "
        "только delete по ключу — то же, что Cache::forget(), когда кэш "
        "лежит в базе. На боевом кэш в файлах, и таблицу это не трогает"
    ),
    # Этап 7 (деньги). Хозяин таблиц — Laravel, пока месяц сверки не
    # пройдёт без расхождений; Django пишет через те же службы: касса,
    # колбэки Uzum и разделы денег в админке
}

#: Какие из SHARED_WRITES разрешены прямо сейчас. ContextVar, а не
#: глобальная переменная: разрешение не должно утечь в соседний поток
#: или запрос, пока блок с ним работает.
_allowed: ContextVar[frozenset[str]] = ContextVar("savdex_allowed_writes", default=frozenset())


@contextmanager
def allowed_writes(*tables: str) -> Iterator[None]:
    """
    Разрешить запись в перечисленные чужие таблицы на время блока.

    Разрешение узкое намеренно: не «Django может писать в users», а
    «вот этот блок кода может». Всё остальное в том же процессе
    по-прежнему упирается в предохранитель.
    """
    # Своя таблица разрешения не требует: блок, заявивший её, пока она
    # была чужой, после перехода хозяина просто работает дальше
    unknown = [t for t in tables if t not in SHARED_WRITES and t not in OWNED_TABLES]

    if unknown:
        raise ValueError(
            f"Запись в {', '.join(unknown)} не заявлена в SHARED_WRITES "
            "(savdex/guards.py) — сначала объясните там, почему она безопасна."
        )

    token = _allowed.set(_allowed.get() | frozenset(tables))

    try:
        yield
    finally:
        _allowed.reset(token)


class WriteToForeignTableError(RuntimeError):
    """Попытка записи в таблицу, которой Django ещё не владеет."""


class MigrationFromDjangoError(RuntimeError):
    """Попытка изменить схему из Django."""


# ── Разбор запроса ──────────────────────────────────────────────────

_WRITE = re.compile(
    r"""^\s*
    (?:
        insert \s+ into \s+ (?P<insert>[`"\[]?[\w.]+[`"\]]?)
      | update \s+ (?:only \s+)? (?P<update>[`"\[]?[\w.]+[`"\]]?)
      | delete \s+ from \s+ (?P<delete>[`"\[]?[\w.]+[`"\]]?)
      | truncate \s+ (?:table \s+)? (?P<truncate>[`"\[]?[\w.]+[`"\]]?)
    )""",
    re.IGNORECASE | re.VERBOSE,
)

_DDL = re.compile(r"^\s*(create|alter|drop|rename)\s", re.IGNORECASE)


def table_of(sql: str) -> str | None:
    """Таблица, в которую пишет запрос. None — запрос не пишет."""
    match = _WRITE.match(sql)

    if match is None:
        return None

    raw = next(value for value in match.groupdict().values() if value)

    # Кавычки ставят все драйверы по-разному, схема нас не различает:
    # одна база, один пользователь
    return raw.strip('`"[]').rsplit(".", maxsplit=1)[-1].lower()


def check(sql: str) -> None:
    """Пропустить запрос или объяснить, почему нельзя."""
    if _DDL.match(sql):
        raise MigrationFromDjangoError(
            "Схему базы меняет только Laravel — database/migrations "
            "(правило 4.2 в docs/migration-to-python.md). "
            f"Запрос: {sql[:120]}"
        )

    table = table_of(sql)

    if (
        table is None
        or table in OWNED_TABLES
        or table in APPEND_ONLY_SHARED
        or table in _allowed.get()
    ):
        return

    raise WriteToForeignTableError(
        f"Таблица «{table}» принадлежит Laravel, Django её только читает "
        "(правило 4.1 в docs/migration-to-python.md). "
        "Если её хозяин действительно переходит — сначала перенесите "
        "правила модели из раздела 5, потом добавьте таблицу "
        "в OWNED_TABLES."
    )


# ── Подключение к Django ────────────────────────────────────────────


def guard(
    execute: Callable[[str, Any, bool, dict[str, Any]], Any],
    sql: str,
    params: Any,  # noqa: ANN401
    many: bool,
    context: dict[str, Any],
) -> Any:  # noqa: ANN401
    """Обёртка вокруг каждого запроса к базе."""
    check(sql)

    return execute(sql, params, many, context)


@receiver(connection_created)
def install_guard(connection: BaseDatabaseWrapper, **kwargs: Any) -> None:
    """
    Повесить предохранитель на соединение, как только оно открылось.

    Обёртка вокруг запроса, а не сигнал модели: сигнал ловит только
    записи через ORM, а обойти его можно `cursor.execute` — то есть
    ровно там, где руки чешутся больше всего.
    """
    if guard not in connection.execute_wrappers:
        connection.execute_wrappers.append(guard)


class LaravelOwnsSchema:
    """
    Маршрутизатор базы: миграции Django не применяются никогда.

    Второй замок к тому же правилу 4.2. Предохранитель выше поймал бы
    сам запрос `CREATE TABLE`, но `manage.py migrate` должен
    останавливаться раньше — до того, как начнёт что-то делать.
    """

    def allow_migrate(
        self,
        db: str,
        app_label: str,
        model_name: str | None = None,
        **hints: Any,
    ) -> bool:
        return False
