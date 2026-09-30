"""
Ход переноса на Python — для главной админки на Django.

Заказчик хотел видеть, как идёт перенос, не читая документы. Здесь —
карта таблиц по этапам (docs/migration-to-python.md, раздел 6) и то,
что из неё уже принадлежит Django: сколько таблиц, какие разделы
админки, какие команды.

Источник правды о хозяине таблицы — guards.OWNED_TABLES: по нему же
работает предохранитель записи, так что страница не может показать
перенесённым то, во что Django на деле писать не может. Совпадение
карты с настоящей схемой базы сверяет tests/test_progress_schema.py.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from savdex.guards import OWNED_TABLES

#: Таблицы, у которых хозяин не меняется никогда: инфраструктура
#: Laravel. sessions — особый случай этапа 3 (Django её только читает)
SHARED: frozenset[str] = frozenset(
    {
        "cache",
        "cache_locks",
        "jobs",
        "job_batches",
        "failed_jobs",
        "password_reset_tokens",
        "sessions",
        "migrations",
        # Очередь машинного перевода: ставят в неё страницы, переводит
        # задача Laravel translations:fill
        "content_translations",
    }
)


@dataclass(frozen=True)
class Stage:
    number: int
    title: str
    tables: tuple[str, ...] = ()
    #: Команды (этап 1): сколько перенесено из скольких
    commands: tuple[str, ...] = ()
    #: Таблицы этапа, которые по решению заказчика остаются за Laravel
    #: или переезжают позже — с причиной
    kept: dict[str, str] = field(default_factory=dict)
    note: str = ""
    #: Этап без своих таблиц (3) считается по шагам: названия и сколько
    #: из них сделано
    steps: tuple[str, ...] = ()
    steps_done: int = 0


STAGES: tuple[Stage, ...] = (
    Stage(
        1,
        "Команды и диагностика",
        commands=(
            "savdex:check-postgres",
            "savdex:uzum-ping",
            "savdex:export-xlsx",
            "savdex:admin",
        ),
    ),
    Stage(
        2,
        "Справочники и содержимое",
        tables=(
            "countries",
            "country_translations",
            "cities",
            "city_translations",
            "categories",
            "category_translations",
            "category_fields",
            "company_types",
            "company_type_translations",
            "promotion_types",
            "plans",
            "credit_packs",
            "payment_methods",
            "promo_codes",
            "pages",
            "landing_blocks",
            "news_posts",
            "faq_items",
            "settings",
            "banners",
            "banner_images",
        ),
        kept={
            "category_fields": "поля категорий заводит только сидер Laravel",
            "promotion_types": "в админке не правятся — решение заказчика",
            "payment_methods": "в админке не правятся — решение заказчика",
            "promo_codes": "сайт пишет в них сам — переезжают с кабинетом, этап 5",
        },
    ),
    Stage(
        3,
        "Публичные страницы, только чтение",
        note="Своих таблиц нет — считается по шагам. Django узнаёт, кто вошёл "
        "на сайте, и отдаёт все страницы, которые ничего не пишут: главную, "
        "«Помощь», «Инструкцию», «Правила», новости, «О компании», «Контакты», "
        "«Страны», «Партнёры», юридические документы, тарифы и отзывы. Визитки компаний "
        "и каталог пишут статистику просмотров — они переезжают на этапе 4.",
        steps=(
            "Django узнаёт, кто вошёл на сайте",
            "Первая страница сайта отдаётся Django",
            "Остальные страницы только для чтения",
        ),
        steps_done=3,
    ),
    Stage(
        4,
        "Каталог",
        tables=(
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
        ),
    ),
    Stage(
        5,
        "Кабинет",
        tables=(
            "users",
            "login_attempts",
            "companies",
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
            "user_notifications",
            "notification_preferences",
            "broadcasts",
        ),
    ),
    Stage(
        6,
        "Админка",
        tables=(
            "admin_actions",
            "activity_events",
            "crm_leads",
            "crm_deals",
            "crm_contacts",
            "crm_tasks",
            "crm_communications",
            "support_tickets",
            "support_messages",
            "imports",
            "exports",
            "failed_import_rows",
        ),
        kept={
            "admin_actions": "журнал пишут обе админки, пока Laravel не выключен",
            "activity_events": "ленту компании пишет и кабинет Laravel — общая до его выключения",
            "imports": "служебная таблица Filament: Django загружает файлы без неё",
            "exports": "служебная таблица Filament: Django выгружает сразу файлом",
            "failed_import_rows": "служебная таблица Filament: отчёт Django — на странице загрузки",
        },
    ),
    Stage(
        7,
        "Деньги",
        tables=(
            "payments",
            "payment_transactions",
            "refunds",
            "subscriptions",
            "wallets",
            "wallet_transactions",
            "promotions",
        ),
        note="Касса, обратные вызовы шлюза и все денежные разделы админки уже на Django. "
        "Хозяин таблиц — Laravel, пока ежедневная сверка «Django против Laravel» не "
        "проработает месяц без расхождений.",
    ),
)

#: Все таблицы, которые переезжают по этапам
MOVING: frozenset[str] = frozenset(t for stage in STAGES for t in stage.tables)


@dataclass(frozen=True)
class StageProgress:
    stage: Stage
    done: int
    total: int
    kept: dict[str, str]

    @property
    def percent(self) -> int:
        return round(100 * self.done / self.total) if self.total else 0

    @property
    def state(self) -> str:
        """«Сделан», «идёт» или «впереди» — для подписи и цвета."""
        if self.total and self.done >= self.total:
            return "done"

        return "active" if self.done else "ahead"


def stage_progress(owned: frozenset[str] = OWNED_TABLES) -> list[StageProgress]:
    """
    Сколько сделано на каждом этапе.

    Команды этапа 1 — все на Python (Django-версии работают на боевом
    сервере). Таблицы, оставленные за Laravel решением заказчика, этап
    не задерживают: они считаются в «оставлено», а не в «осталось».
    """
    result = []

    for stage in STAGES:
        if stage.commands:
            done = total = len(stage.commands)
        elif stage.steps:
            done, total = stage.steps_done, len(stage.steps)
        else:
            planned = [t for t in stage.tables if t not in stage.kept]
            done, total = sum(t in owned for t in planned), len(planned)

        result.append(StageProgress(stage, done, total, dict(stage.kept)))

    return result


def summary(owned: frozenset[str] = OWNED_TABLES) -> dict[str, object]:
    """Всё для страницы: общий счёт, этапы и что уже на Python."""
    planned = MOVING - {t for stage in STAGES for t in stage.kept}
    done = len(owned & planned)

    return {
        "tables_done": done,
        "tables_total": len(planned),
        "percent": round(100 * done / len(planned)) if planned else 0,
        "stages": stage_progress(owned),
    }
