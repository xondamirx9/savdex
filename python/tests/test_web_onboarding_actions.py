"""
Второй шаг регистрации, пропуск, «Оцените SavdEx» и удаление учётки на
Django: ответ, сессия после него и что записано в базу.

- Компания со второго шага: проверка (ИНН по правилу Tin — у физлица
  и ПИНФЛ, одна компания на ИНН, до пяти направлений), форма
  собственности из регистрации, адрес из названия, направления,
  владелец, переход к подтверждению почты; у кого компания есть —
  в кабинет. Пропуск — туда же с предупреждением.
- Отзыв о площадке: проверка, кто может, премодерация и проверка
  текста, правка своего — снова на проверку.
- Удаление учётки: пароль ещё раз, объявления владельца — в архив,
  выход, мягкое удаление, новая сессия.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from .factories import категория, компания, объявление
from .pg_admin import sql, нужна_база, свежая_база, страна
from .test_web_forms import отправить, учётка
from .web_site import ПАРОЛЬ, адрес

pytestmark = нужна_база

ПОЧТА = "onboard@savdex.uz"


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    uz = страна("uz", {"ru": "Узбекистан"})
    страна("kz", {"ru": "Казахстан"})
    sql(
        "insert into cities (country_id, slug, sort, is_active, created_at, updated_at) "
        "values (%s, 'tashkent', 0, true, now(), now())",
        [uz],
    )
    компания(slug="mine", country_id=uz, tin="301234567")
    компания(slug="blocked", status="blocked")

    for slug in ("cement", "metal", "wood", "glass", "paint", "tiles"):
        категория(slug=slug)

    with адрес() as root:
        yield root


def _номер(table: str, slug: str) -> int:
    return int(sql(f"select id from {table} where slug = %s", [slug])[0][0])


def _страна(code: str) -> int:
    return int(sql("select id from countries where code = %s", [code])[0][0])


def _город() -> int:
    return int(sql("select id from cities where slug = 'tashkent'")[0][0])


def пользователь(**поля: Any) -> int:
    return учётка(
        ПОЧТА,
        **{
            "status": "active",
            "company_id": None,
            "company_role": "owner",
            "account_type": "legal",
            "email_verified_at": "2026-01-01 00:00:00",
            "deleted_at": None,
            **поля,
        },
    )


def _журнал() -> list[Any]:
    return [
        (a, s, label, re.sub(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", "T", ch or ""))
        for a, s, label, ch in sql(
            "select action, section, subject_label, changes::text from admin_actions order by id"
        )
    ]


def _сессия(итог: dict[str, Any]) -> dict[str, Any]:
    return dict(json.loads(итог["сессия"]["payload"]))


def ошибки(итог: dict[str, Any]) -> dict[str, list[str]]:
    """Ошибки проверки в сессии: поле → тексты."""
    errors = _сессия(итог).get("errors") or {"default": {"messages": {}}}

    return dict(errors["default"]["messages"])


def назад(итог: dict[str, Any], сайт: str) -> bool:
    """Ответ — переход назад, на страницу формы (Referer)."""
    return итог["ответ"]["status"] == 302 and (
        итог["ответ"]["headers"]["location"] == сайт + "/cabinet/settings"
    )


#: Компания со второго шага
СОЗДАНА = "Компания создана. Осталось подтвердить почту — и можно публиковать объявления."


# ── Второй шаг регистрации ──────────────────────────────────────────


def сброс_компаний(**поля: Any) -> Callable[[], None]:
    def run() -> None:
        sql("delete from admin_actions")
        sql("update users set company_id = null where email = %s", [ПОЧТА])
        sql("delete from companies where slug not in ('mine', 'blocked')")
        sql("select setval('companies_id_seq', (select max(id) from companies) + 1, false)")
        sql("select setval('company_category_id_seq', 1, false)")
        пользователь(**поля)

    return run


def снимок_компаний() -> Any:
    return {
        "companies": sql(
            "select id, slug, name, type, legal_form, country_id, city_id, tin, primary_role, "
            "custom_category, status, search_text, created_at is not null "
            "from companies where slug not in ('mine', 'blocked') order by id"
        ),
        "categories": sql(
            "select id, company_id, category_id, created_at, updated_at from company_category "
            "order by id"
        ),
        "user": sql(
            "select company_id is not null, company_role from users where email = %s", [ПОЧТА]
        ),
        "journal": _журнал(),
    }


def верно() -> dict[str, Any]:
    return {
        "name": "  Цемент Плюс ",
        "type": "manufacturer",
        "country_id": _страна("uz"),
        "city_id": _город(),
        "tin": "302345678",
        "primary_role": "supplier",
        "categories": [_номер("categories", "cement"), str(_номер("categories", "metal"))],
        "custom_category": "Бетон",
    }


#: Ошибка поля ИНН
def _инн(текст: str) -> dict[str, list[str]]:
    return {"tin": [текст]}


#: Текст правила exists — общий, без имени поля
НЕ_НАЙДЕНО = "Выбранное значение не найдено."


@pytest.mark.parametrize(
    ("правка", "поля", "ждём"),
    [
        # ждём: (форма собственности, ИНН) созданной компании — или ошибки
        ({}, {}, ("legal", "302345678")),
        ({}, {"account_type": "individual"}, ("individual", "302345678")),
        # Фрилансеру тип компании не нужен
        ({"type": None}, {"account_type": "freelancer"}, ("freelancer", "302345678")),
        ({"type": None}, {}, {"type": ["Выберите тип компании"]}),
        (
            {"type": None, "name": ""},
            {"account_type": "individual"},
            {"name": ["Укажите имя, которое увидят партнёры"]},
        ),
        # ПИНФЛ — только у физлица
        (
            {"tin": "12345678901234"},
            {"account_type": "individual"},
            ("individual", "12345678901234"),
        ),
        ({"tin": "12345678901234"}, {}, _инн("ИНН (СТИР) в Узбекистане — ровно 9 цифр.")),
        (
            {"tin": "3023456"},
            {"account_type": "individual"},
            _инн("У физического лица в Узбекистане ИНН — 9 цифр, ПИНФЛ — 14 цифр."),
        ),
        ({"tin": "30234567a"}, {}, _инн("ИНН состоит только из цифр.")),
        ({"tin": "111111111"}, {}, _инн("Указан недействительный ИНН.")),
        # Одна компания на ИНН: 301234567 — у «mine»
        (
            {"tin": "301234567"},
            {},
            _инн("Компания с таким номером из этой страны уже зарегистрирована на площадке"),
        ),
        ({"tin": "12345", "country_id": "kz"}, {}, _инн("БИН/ИИН в Казахстане — 12 цифр.")),
        ({"tin": "1234-5678 9012", "country_id": "kz"}, {}, ("legal", "123456789012")),
        # Неизвестный вид учётки — юрлицо; ИНН необязателен
        ({"tin": None}, {"account_type": "robot"}, ("legal", None)),
        # Нечисловой город у Laravel был ошибкой 500 (exists сравнивал строку
        # с числовым столбцом), у Django — ошибка проверки: здесь число
        (
            {"country_id": 99999, "city_id": 99998},
            {},
            {"country_id": [НЕ_НАЙДЕНО], "city_id": [НЕ_НАЙДЕНО]},
        ),
        ({"primary_role": "seller"}, {}, {"primary_role": ["Выберите значение из списка."]}),
        # Строка вместо списка: не массив, а max:5 у строки — длина «cement»
        (
            {"categories": "cement"},
            {},
            {
                "categories": [
                    "Неверный формат значения.",
                    "Не больше пяти категорий — иначе профиль перестаёт что-либо говорить "
                    "о компании",
                ]
            },
        ),
        (
            {"categories": ["all6"]},
            {},
            {
                "categories": [
                    "Не больше пяти категорий — иначе профиль перестаёт что-либо говорить "
                    "о компании"
                ]
            },
        ),
        (
            {"categories": [99999, "abc"]},
            {},
            {"categories.0": [НЕ_НАЙДЕНО], "categories.1": ["Укажите целое число."]},
        ),
        # Повтор направления — одна строка
        ({"categories": ["dup"]}, {}, ("legal", "302345678")),
        (
            {"custom_category": "x" * 81, "name": "Ц"},
            {},
            {"name": ["Не короче 2 символов."], "custom_category": ["Не длиннее 80 символов."]},
        ),
        ({"categories": None}, {}, {"categories": ["Неверный формат значения."]}),
    ],
)
def test_второй_шаг(сайт, правка, поля, ждём):
    body = {**верно(), **правка}

    if body.get("country_id") == "kz":
        body["country_id"] = _страна("kz")

    if body.get("categories") == ["all6"]:
        body["categories"] = [_номер("categories", s) for s in ("cement", "metal", "wood")] + [
            _номер("categories", s) for s in ("glass", "paint", "tiles")
        ]

    if body.get("categories") == ["dup"]:
        body["categories"] = [_номер("categories", "wood")] * 2

    uid = пользователь(**поля)
    итог = отправить(
        сайт, "/onboarding/company", сброс_компаний(**поля), снимок_компаний, uid=uid, body=body
    )
    база = итог["база"]

    if isinstance(ждём, dict):
        assert назад(итог, сайт)
        assert ошибки(итог) == ждём
        assert база["companies"] == [] and база["categories"] == []
        assert база["user"] == [(False, "owner")]

        return

    форма, инн = ждём
    assert итог["ответ"]["headers"]["location"] == сайт + "/verify-email"
    assert _сессия(итог)["success"] == СОЗДАНА
    [company] = база["companies"]
    # Адрес — из названия; название без пробелов по краям
    assert company[1:5] == ("tsement-plius", "Цемент Плюс", body["type"], форма)
    assert (company[7], company[8], company[9], company[10]) == (инн, "supplier", "Бетон", "active")
    assert len(база["categories"]) == (1 if правка.get("categories") == ["dup"] else 2)
    assert база["user"] == [(True, "owner")]
    # Не сотрудник — журнал администратора пуст
    assert база["journal"] == []


@pytest.mark.parametrize("admin", [False, True])
def test_второй_шаг_журнал_администратора(сайт, admin):
    uid = пользователь(is_admin=admin)
    итог = отправить(
        сайт,
        "/onboarding/company",
        сброс_компаний(is_admin=admin),
        снимок_компаний,
        uid=uid,
        body=верно(),
    )
    журнал = итог["база"]["journal"]

    assert итог["ответ"]["headers"]["location"] == сайт + "/verify-email"

    if not admin:
        assert журнал == []

        return

    # Сотрудник, заводящий компанию, пишет журнал: компания и его учётка
    assert [(a, s, label) for a, s, label, _ in журнал] == [
        ("created", "companies", "Цемент Плюс"),
        ("updated", "users", f"Покупатель {ПОЧТА}"),
    ]
    assert json.loads(журнал[0][3])["after"]["tin"] == "302345678"
    assert json.loads(журнал[1][3])["before"] == {"company_id": None}


def test_второй_шаг_компания_уже_есть(сайт):
    uid = пользователь()
    mine = _номер("companies", "mine")
    итог = отправить(
        сайт,
        "/onboarding/company",
        сброс_компаний(company_id=mine, company_role="owner"),
        снимок_компаний,
        uid=uid,
        body=верно(),
    )

    # Вторую компанию не завести — в кабинет
    assert итог["ответ"]["status"] == 302
    assert итог["ответ"]["headers"]["location"] == сайт + "/cabinet"
    assert итог["база"]["companies"] == []
    assert sql("select company_id from users where id = %s", [uid]) == [(mine,)]


@pytest.mark.parametrize("uid", [True, None])
def test_пропустить(сайт, uid):
    номер = пользователь()
    итог = отправить(
        сайт,
        "/onboarding/skip",
        сброс_компаний(),
        снимок_компаний,
        uid=номер if uid else None,
        body={},
    )

    assert итог["база"]["companies"] == []

    if uid is None:
        assert итог["ответ"]["headers"]["location"] == сайт + "/login"
    else:
        assert итог["ответ"]["headers"]["location"] == сайт + "/verify-email"
        assert _сессия(итог)["warning"] == (
            "Данные компании можно заполнить позже в кабинете. "
            "Без них публикация объявлений недоступна."
        )


# ── «Оцените SavdEx» ────────────────────────────────────────────────


def сброс_отзыва(
    *, был: bool = False, премодерация: bool | None = None, **поля: Any
) -> Callable[[], None]:
    def run() -> None:
        sql("delete from platform_reviews")
        sql("select setval('platform_reviews_id_seq', 1, false)")
        sql("delete from settings where key = 'reviews_premoderation'")
        sql("delete from cache")

        if премодерация is not None:
            sql(
                "insert into settings (key, label, type, value, created_at, updated_at) "
                "values ('reviews_premoderation', 'Премодерация', 'boolean', %s, now(), now())",
                [json.dumps(премодерация)],
            )

        uid = пользователь(**поля)

        if был:
            sql(
                "insert into platform_reviews (user_id, company_id, rating, rating_usability, "
                "body, status, moderator_note, moderated_by, moderated_at, created_at, "
                "updated_at) values (%s, null, 5, 4, 'Прежний текст отзыва о площадке, "
                "достаточно длинный', 'hidden', 'Уберите ссылку', 1, now(), "
                "now() - interval '1 day', now() - interval '1 day')",
                [uid],
            )

    return run


def снимок_отзыва() -> Any:
    return sql(
        "select id, user_id is not null, company_id, rating, rating_usability, rating_search, "
        "rating_support, body, status, screening_flags, moderator_note, moderated_by, "
        "moderated_at, updated_at > now() - interval '1 hour' from platform_reviews order by id"
    )


ОТЗЫВ = {
    "rating": 5,
    "rating_usability": "4",
    "rating_search": 0,
    "body": "  Удобно искать поставщиков цемента, быстро отвечают.  ",
}


НА_ПРОВЕРКУ = (
    "Отзыв отправлен на проверку. Обычно она занимает несколько часов — после этого отзыв "
    "появится на странице отзывов о площадке."
)
ОПУБЛИКОВАН = "Спасибо! Отзыв опубликован."
КОРОТКО = (
    "Отзыв в пару слов ничего не говорит следующему покупателю — опишите, что было хорошо и что нет"
)
ТЕКСТ = "Удобно искать поставщиков цемента, быстро отвечают."


@pytest.mark.parametrize(
    ("body", "настройка", "ждём"),
    [
        # ждём: ошибки проверки, {"error": …} — отказ, иначе (сообщение, статус отзыва)
        ({}, {}, {"rating": ["Поставьте общую оценку"], "body": ["Напишите, как прошла работа"]}),
        (
            {"rating": 6, "body": "коротко", "rating_support": 9},
            {},
            {
                "rating": ["Значение должно быть от 1 до 5."],
                "rating_support": ["Значение должно быть от 0 до 5."],
                "body": [КОРОТКО],
            },
        ),
        (
            {"rating": "4.5", "body": ["x"]},
            {},
            {"rating": ["Укажите целое число."], "body": ["Укажите текст.", КОРОТКО]},
        ),
        ({"rating": 4.0, "body": ОТЗЫВ["body"]}, {}, (НА_ПРОВЕРКУ, "moderation")),
        (ОТЗЫВ, {}, (НА_ПРОВЕРКУ, "moderation")),
        (ОТЗЫВ, {"премодерация": False}, (ОПУБЛИКОВАН, "published")),
        # Правка своего скрытого отзыва — та же строка, пометки модератора сняты
        (ОТЗЫВ, {"премодерация": False, "был": True}, (ОПУБЛИКОВАН, "published")),
        (ОТЗЫВ, {"был": True}, (НА_ПРОВЕРКУ, "moderation")),
        # Контакты в тексте — на проверку и без премодерации
        (
            {**ОТЗЫВ, "body": "Пишите мне на почту test@mail.ru, всё расскажу подробно"},
            {"премодерация": False},
            (
                "Отзыв отправлен на проверку: в тексте есть контакты: телефон, почта или "
                "ссылка. Модератор посмотрит его вручную.",
                "moderation",
            ),
        ),
        (
            ОТЗЫВ,
            {"email_verified_at": None},
            {"error": "Подтвердите почту, чтобы оставлять отзывы."},
        ),
        # Заблокированного блокировка выводит из сессии — на вход, без отзыва
        (ОТЗЫВ, {"status": "blocked"}, "на вход"),
        (ОТЗЫВ, {"company": "blocked"}, {"error": "Ваша учётная запись заблокирована."}),
        (ОТЗЫВ, {"company": "mine"}, (НА_ПРОВЕРКУ, "moderation")),
    ],
)
def test_отзыв_о_площадке(сайт, body, настройка, ждём):
    настройка = dict(настройка)

    if "company" in настройка:
        настройка["company_id"] = _номер("companies", настройка.pop("company"))

    uid = пользователь()
    итог = отправить(
        сайт,
        "/reviews/new",
        сброс_отзыва(**настройка),
        снимок_отзыва,
        uid=uid,
        body=body,
    )
    отзывы = итог["база"]

    if ждём == "на вход":
        assert итог["ответ"]["headers"]["location"] == сайт + "/login"
        assert отзывы == []

        return

    assert назад(итог, сайт)

    if isinstance(ждём, dict) and "error" in ждём:
        assert _сессия(итог)["error"] == ждём["error"]
        assert ошибки(итог) == {}
        assert len(отзывы) == (1 if настройка.get("был") else 0)

        return

    if isinstance(ждём, dict):
        assert ошибки(итог) == ждём
        assert отзывы == []

        return

    сообщение, статус = ждём
    assert _сессия(итог)["success"] == сообщение
    [отзыв] = отзывы
    # Одна строка на пользователя: правка — та же строка
    assert отзыв[0] == 1
    assert отзыв[2] == настройка.get("company_id")
    assert отзыв[3] == int(float(body["rating"]))
    assert отзыв[8] == статус
    assert отзыв[9] == (
        "В тексте есть контакты: телефон, почта или ссылка" if "@" in body["body"] else None
    )
    # Модерация прошлой версии снята, правка — сейчас
    assert отзыв[10:14] == (None, None, None, True)

    if "@" not in body["body"]:
        assert отзыв[7] == ТЕКСТ


# ── Удалить учётную запись ──────────────────────────────────────────


def сброс_удаления(**поля: Any) -> Callable[[], None]:
    def run() -> None:
        sql("delete from admin_actions")
        sql("delete from listings")
        mine = _номер("companies", "mine")
        for status in ("active", "active", "draft", "archived"):
            объявление(company_id=mine, status=status)

        объявление(status="active")
        sql("update listings set updated_at = now() - interval '1 day'")
        пользователь(**поля)
        sql(
            "update users set remember_token = 'старый', updated_at = now() - interval '1 day' "
            "where email = %s",
            [ПОЧТА],
        )

    return run


def снимок_удаления() -> Any:
    return {
        "user": sql(
            "select deleted_at is not null, updated_at > now() - interval '1 hour', "
            "remember_token = 'старый' from users where email = %s",
            [ПОЧТА],
        ),
        "listings": sql(
            "select company_id is not null, status, updated_at > now() - interval '1 hour' "
            "from listings order by id"
        ),
        "journal": _журнал(),
    }


@pytest.mark.parametrize(
    ("body", "поля"),
    [
        ({}, {}),
        ({"password": ["x"]}, {}),
        ({"password": "неверный"}, {}),
        ({"password": ПАРОЛЬ}, {"company": "mine", "company_role": "owner"}),
        ({"password": ПАРОЛЬ}, {"company": "mine", "company_role": "manager"}),
        ({"password": ПАРОЛЬ}, {"company": "mine", "company_role": "owner", "is_admin": True}),
        ({"password": ПАРОЛЬ}, {}),
    ],
)
def test_удалить_учётку(сайт, body, поля):
    поля = dict(поля)

    if "company" in поля:
        поля["company_id"] = _номер("companies", поля.pop("company"))

    uid = пользователь(**поля)
    итог = удаление(сайт, сброс_удаления(**поля), uid, body)
    db = итог["db"]

    assert итог["status"] == 302
    assert итог["cookies"] == ["XSRF-TOKEN", "savdex-session"]

    if body.get("password") != ПАРОЛЬ:
        # Ошибка проверки — назад, ничего не удалено, вход на месте
        assert итог["location"] == сайт + "/cabinet/settings"
        assert итог["old_session"] is True
        assert итог["session"]["user_id"] == uid
        assert '"password":[' in итог["session"]["payload"]
        assert db["user"] == [(False, False, True)]
        assert all(not свежее for _, _, свежее in db["listings"])

        return

    # Мягкое удаление, выход, новая сессия; remember_token сменён
    assert итог["location"] == сайт
    assert итог["old_session"] is False
    assert итог["session"]["user_id"] is None
    assert '"success":' in итог["session"]["payload"]
    assert db["user"] == [(True, True, False)]
    # Владелец уносит в архив живые объявления компании; чужие и черновики — на месте
    архив = поля.get("company_role") == "owner"
    assert [статус for _, статус, _ in db["listings"]] == (
        ["archived", "archived", "draft", "archived", "active"]
        if архив
        else ["active", "active", "draft", "archived", "active"]
    )
    # Журнал — только у сотрудника, и токен в нём скрыт
    assert [(a, s, label) for a, s, label, _ in db["journal"]] == (
        [("updated", "users", f"Покупатель {ПОЧТА}")] if поля.get("is_admin") else []
    )


def удаление(
    сайт: str, подготовка: Callable[[], None], uid: int, body: dict[str, Any]
) -> dict[str, Any]:
    """Сессия после удаления — новая: номер берётся из куки ответа."""
    from savdex import laravel_session

    from .test_web_forms import SID, ТОКЕН, inertia
    from .web_site import СЕССИЯ, завести, из_django, кука, куки_ответа, строка

    подготовка()
    завести(SID, {"_token": ТОКЕН, laravel_session.LOGIN_KEY: uid})
    ответ = из_django(
        сайт,
        "/cabinet/settings/delete",
        {СЕССИЯ: кука(СЕССИЯ, SID)},
        {**inertia(), "Referer": сайт + "/cabinet/settings", "User-Agent": "savdex-parity"},
        method="POST",
        body=json.dumps(body),
        content_type="application/json",
    )
    assert ответ["status"] < 500, ответ["body"][:3000]
    sid = (куки_ответа(ответ).get(СЕССИЯ) or {}).get("value")
    сессия = строка(sid) if sid else None

    return {
        "status": ответ["status"],
        "location": ответ["headers"].get("location"),
        "cookies": sorted(ответ["cookies"]),
        "session": None
        if сессия is None
        else {"payload": сессия["payload"], "user_id": сессия["user_id"]},
        "old_session": строка(SID) is not None,
        "db": снимок_удаления(),
    }


# ── Второй шаг у юрлица с компанией из регистрации ─────────────────


def сброс_дополнения(*, город: bool = False, форма: str = "legal") -> Callable[[], None]:
    """Компания заведена при регистрации: название, ИНН, два раздела, без города."""

    def run() -> None:
        сброс_компаний()()
        [(cid,)] = sql(
            "insert into companies (name, slug, legal_form, tin, primary_role, status, "
            "custom_category, city_id, created_at, updated_at) values ('Цемент Плюс', "
            "'cement-plus', %s, '302345678', 'both', 'active', 'Бетон', %s, "
            "now() - interval '1 day', now() - interval '1 day') returning id",
            [форма, _город() if город else None],
        )
        sql(
            "insert into company_category (company_id, category_id) select %s, id "
            "from categories where slug in ('cement', 'metal')",
            [cid],
        )
        пользователь(company_id=cid)

    return run


def снимок_дополнения() -> Any:
    return {
        "companies": sql(
            "select slug, name, type, country_id, city_id, primary_role, custom_category, "
            "updated_at > now() - interval '1 hour' from companies where slug = 'cement-plus'"
        ),
        "categories": sql(
            "select c.slug from company_category cc join categories c on c.id = cc.category_id "
            "join companies k on k.id = cc.company_id where k.slug = 'cement-plus' order by c.slug"
        ),
        "journal": _журнал(),
    }


@pytest.mark.parametrize(
    ("правка", "настройка", "ждём"),
    [
        # ждём: направления после шага — или ошибки; None — шаг уже пройден
        ({}, {}, ["cement", "metal"]),
        # К двум прежним — новые, но всего не больше пяти
        (
            {"categories": ["wood", "glass", "paint", "tiles"]},
            {},
            ["cement", "glass", "metal", "paint", "wood"],
        ),
        ({"categories": ["cement"], "custom_category": None}, {}, ["cement", "metal"]),
        (
            {"type": None, "city_id": None},
            {},
            {"type": ["Выберите тип компании"], "city_id": ["Выберите город"]},
        ),
        # Город уже указан или компания не юрлица — второй шаг пройден
        ({}, {"город": True}, None),
        ({}, {"форма": "individual"}, None),
    ],
)
def test_дополнение_компании(сайт, правка, настройка, ждём):
    body = {**верно(), "custom_category": "Сухие смеси", **правка}

    if body.get("categories"):
        body["categories"] = [
            _номер("categories", s) if isinstance(s, str) and not s.isdigit() else s
            for s in body["categories"]
        ]

    uid = пользователь()
    итог = отправить(
        сайт,
        "/onboarding/company",
        сброс_дополнения(**настройка),
        снимок_дополнения,
        uid=uid,
        body=body,
    )
    база = итог["база"]
    [company] = база["companies"]

    if ждём is None:
        assert итог["ответ"]["headers"]["location"] == сайт + "/cabinet"
        # Ничего не тронуто
        assert company[2] is None and company[7] is False
        assert база["categories"] == [("cement",), ("metal",)]

        return

    if isinstance(ждём, dict):
        assert назад(итог, сайт)
        assert ошибки(итог) == ждём
        assert company[7] is False

        return

    # Дозаполнено недостающее: тип, страна, город, роль; адрес и название — прежние
    assert итог["ответ"]["headers"]["location"] == сайт + "/verify-email"
    assert company[:3] == ("cement-plus", "Цемент Плюс", "manufacturer")
    assert company[3:6] == (_страна("uz"), _город(), "supplier")
    # Пустое своё направление не стирает прежнее
    assert company[6] == ("Бетон" if "custom_category" in правка else "Сухие смеси")
    assert company[7] is True
    assert [c for (c,) in база["categories"]] == ждём
