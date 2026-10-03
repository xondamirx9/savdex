"""
Этап 5, шаг 21: первые формы кабинета на Django — ответ (переход,
страница ошибки), строка sessions после ответа (сообщения, ошибки
проверки, ввод) и то, что записано в базу.

Посредники: без токена CSRF — 419 (кроме Sec-Fetch-Site: same-origin),
токен — из ввода, X-CSRF-TOKEN или зашифрованного X-XSRF-TOKEN; гость —
на вход; частота (throttle:60,1 у избранного).

Формы: прочтение уведомления (адрес внутри площадки — туда, иначе
назад) и всех; избранное (добавить, убрать, счётчик, дневная строка,
журнал администратора); настройки уведомлений (updateOrCreate, ошибки
проверки — тексты Laravel); смена языка.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from savdex import laravel_cache, laravel_session

from .factories import объявление
from .pg_admin import KEY, sql, нужна_база, свежая_база
from .web_site import (  # noqa: F401 — куки_ответа берут отсюда другие проверки
    СЕССИЯ,
    адрес,
    завести,
    из_django,
    кука,
    куки_ответа,
    открыть,
    пользователь,
    строка,
)

pytestmark = нужна_база

SID = "F" * 40
ТОКЕН = "t" * 40


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    with адрес() as root:
        yield root


def учётка(email: str, **поля: Any) -> int:
    found = sql("select id from users where email = %s", [email])
    uid = int(found[0][0]) if found else пользователь(email)
    поля = {"locale": "ru", "must_change_password": False, "is_admin": False, **поля}
    sets = ", ".join(f"{k} = %s" for k in поля)
    sql(f"update users set {sets} where id = %s", [*поля.values(), uid])

    return uid


def xsrf(token: str = ТОКЕН) -> str:
    """Кука XSRF-TOKEN, как её ставит Laravel, — значение для заголовка."""
    return laravel_session.encrypt_cookie("XSRF-TOKEN", token, KEY)


def inertia(**extra: str) -> dict[str, str]:
    """Заголовки формы Inertia: JSON, XHR и зашифрованный токен."""
    return {
        "X-Inertia": "true",
        "X-Requested-With": "XMLHttpRequest",
        "Accept": "text/html, application/xhtml+xml",
        "X-XSRF-TOKEN": xsrf(),
        **extra,
    }


def отправить(
    сайт: str,
    path: str,
    подготовить: Callable[[], None],
    снимок: Callable[[], Any] = lambda: None,
    *,
    uid: int | None = None,
    данные: dict[str, Any] | None = None,
    body: Any = None,
    content_type: str = "application/json",
    headers: dict[str, str] | None = None,
    method: str = "POST",
    env: dict[str, str] | None = None,
    drop: tuple[str, ...] = (),
    чистка: Callable[[str], str] = lambda payload: payload,
) -> dict[str, Any]:
    """
    Отправка формы сайту: подготовить() — данные, затем сессия с токеном
    (и входом uid), запрос к Django. Итог — ответ, строка сессии после
    него и снимок базы (снимок()). Ошибка сервера (5xx) — провал.

    drop и чистка остались от сверки с Laravel и больше ничего не делают.
    """
    del drop, чистка
    payload = {"_token": ТОКЕН, **(данные or {})}

    if uid is not None:
        payload[laravel_session.LOGIN_KEY] = uid

    raw = body if isinstance(body, str) else json.dumps(body if body is not None else {})
    подготовить()
    завести(SID, payload)
    ответ = из_django(
        сайт,
        path,
        {СЕССИЯ: кука(СЕССИЯ, SID)},
        {
            "Referer": сайт + "/cabinet/settings",
            **(headers if headers is not None else inertia()),
        },
        env,
        method=method,
        body=raw,
        content_type=content_type,
    )
    assert ответ["status"] < 500, (ответ["status"], ответ["body"][:3000])

    return {"ответ": ответ, "сессия": строка(SID), "база": снимок()}


def время(value: Any) -> Any:
    """Метка времени в снимке — только «есть или нет»: секунды у сторон разные."""
    return None if value is None else "set"


# ── Посредники ──────────────────────────────────────────────────────


def _уведомления(uid: int) -> Callable[[], None]:
    def подготовить() -> None:
        sql("delete from user_notifications where user_id = %s or id between 900 and 902", [uid])

        for i, url in enumerate(["/cabinet/listings", "https://evil.example/x", None]):
            sql(
                "insert into user_notifications (id, user_id, type, tone, title, url, "
                "created_at, updated_at) values (%s, %s, 'info', 'info', %s, %s, now(), now())",
                [900 + i, uid, f"Уведомление {i}", url],
            )

        sql("update users set locale = 'ru' where id = %s", [uid])

    return подготовить


def _снимок_уведомлений(uid: int) -> Callable[[], Any]:
    return lambda: [
        (i, время(r), время(u))
        for i, r, u in sql(
            "select id, read_at, updated_at from user_notifications where user_id = %s order by id",
            [uid],
        )
    ]


@pytest.mark.parametrize(
    "headers",
    [
        {"X-Inertia": "true", "X-Requested-With": "XMLHttpRequest"},
        {"X-Inertia": "true", "X-XSRF-TOKEN": "garbage"},
        {"X-Inertia": "true", "X-CSRF-TOKEN": "x" * 40},
    ],
)
def test_без_токена_419(сайт, headers):
    uid = учётка("forms-csrf@savdex.uz")
    итог = отправить(
        сайт,
        "/notifications/read-all",
        _уведомления(uid),
        _снимок_уведомлений(uid),
        uid=uid,
        headers=headers,
    )

    assert итог["ответ"]["status"] == 419
    assert all(r is None for _, r, _ in итог["база"])


@pytest.mark.parametrize(
    "headers",
    [
        {"Sec-Fetch-Site": "same-origin"},
        {"X-CSRF-TOKEN": ТОКЕН},
        {"X-Inertia": "true", "X-XSRF-TOKEN": xsrf()},
    ],
)
def test_токен_принят(сайт, headers):
    uid = учётка("forms-token@savdex.uz")
    итог = отправить(
        сайт,
        "/notifications/read-all",
        _уведомления(uid),
        _снимок_уведомлений(uid),
        uid=uid,
        headers=headers,
    )

    assert итог["ответ"]["status"] == 302
    assert all(r == "set" for _, r, _ in итог["база"])


def test_токен_в_теле_формы(сайт):
    uid = учётка("forms-body@savdex.uz")
    итог = отправить(
        сайт,
        "/notifications/read-all",
        _уведомления(uid),
        _снимок_уведомлений(uid),
        uid=uid,
        body=f"_token={ТОКЕН}&x=%20a%20",
        content_type="application/x-www-form-urlencoded",
        headers={},
    )

    assert итог["ответ"]["status"] == 302


def test_гость_на_вход(сайт):
    итог = отправить(сайт, "/notifications/read-all", lambda: None)

    assert итог["ответ"]["headers"]["location"].endswith("/login")
    assert "intended" in итог["сессия"]["payload"]


# ── Уведомления ─────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("номер", "куда"),
    [(900, "/cabinet/listings"), (901, "/cabinet/settings"), (902, "/cabinet/settings")],
)
@pytest.mark.parametrize("prefix", ["", "/uz"])
def test_прочитать_уведомление(сайт, номер, куда, prefix):
    uid = учётка("forms-read@savdex.uz")
    итог = отправить(
        сайт,
        f"{prefix}/notifications/{номер}/read",
        _уведомления(uid),
        _снимок_уведомлений(uid),
        uid=uid,
    )

    assert итог["ответ"]["headers"]["location"].endswith(prefix + куда)
    assert [r for i, r, _ in итог["база"] if i == номер] == ["set"]


def test_чужое_уведомление_404(сайт):
    uid = учётка("forms-read@savdex.uz")
    чужой = учётка("forms-other@savdex.uz")
    итог = отправить(
        сайт,
        "/notifications/900/read",
        _уведомления(чужой),
        _снимок_уведомлений(чужой),
        uid=uid,
    )

    assert итог["ответ"]["status"] == 404


def test_прочитать_все(сайт):
    uid = учётка("forms-all@savdex.uz")
    итог = отправить(
        сайт,
        "/uz/notifications/read-all",
        _уведомления(uid),
        _снимок_уведомлений(uid),
        uid=uid,
    )

    assert итог["ответ"]["headers"]["location"].endswith("/uz/cabinet/settings")
    assert '"success":' in итог["сессия"]["payload"]
    assert [r for _, r, _ in итог["база"]] == ["set", "set", "set"]


# ── Избранное ───────────────────────────────────────────────────────


def _объявление() -> int:
    found = sql("select id from listings where slug = 'fav-listing'")

    if found:
        return int(found[0][0])

    lid = объявление(slug="fav-listing")
    объявление(draft=True, slug="fav-draft")

    return lid


def _избранное(uid: int, lid: int, было: bool, счётчик: int = 3) -> Callable[[], None]:
    def подготовить() -> None:
        sql("delete from favorites where user_id = %s", [uid])
        sql("delete from listing_stats where listing_id = %s", [lid])
        sql("delete from admin_actions where section = 'listings'")
        sql("update listings set favorites_count = %s where id = %s", [счётчик, lid])

        if было:
            sql(
                "insert into favorites (user_id, listing_id, created_at, updated_at) "
                "values (%s, %s, now(), now())",
                [uid, lid],
            )

    return подготовить


def _снимок_избранного(uid: int, lid: int) -> Callable[[], Any]:
    return lambda: {
        "favorites": sql("select listing_id from favorites where user_id = %s", [uid]),
        "count": sql("select favorites_count from listings where id = %s", [lid]),
        "stats": sql(
            "select impressions, views, favorites, unlocks from listing_stats "
            "where listing_id = %s",
            [lid],
        ),
        "journal": sql(
            "select user_id, action, section, subject_type, subject_id, subject_label, "
            "changes::text, ip from admin_actions where section = 'listings' order by id"
        ),
    }


@pytest.mark.parametrize(("было", "счётчик"), [(False, 3), (True, 3), (True, 0)])
@pytest.mark.parametrize("admin", [False, True])
def test_избранное(сайт, было, счётчик, admin):
    uid = учётка("forms-fav@savdex.uz", is_admin=admin)
    lid = _объявление()
    итог = отправить(
        сайт,
        f"/favorites/{lid}",
        _избранное(uid, lid, было, счётчик),
        _снимок_избранного(uid, lid),
        uid=uid,
    )

    assert итог["ответ"]["status"] == 302
    assert bool(итог["база"]["favorites"]) is not было
    assert bool(итог["база"]["journal"]) is (admin and not было)


@pytest.mark.parametrize("slug", ["fav-draft", None])
def test_избранное_не_живое_404(сайт, slug):
    uid = учётка("forms-fav@savdex.uz")
    _объявление()
    lid = int(sql("select id from listings where slug = %s", [slug])[0][0]) if slug else 999999
    итог = отправить(сайт, f"/favorites/{lid}", lambda: None, uid=uid)

    assert итог["ответ"]["status"] == 404


# ── Настройки уведомлений ───────────────────────────────────────────


def _настройки(uid: int) -> Callable[[], None]:
    def подготовить() -> None:
        sql("delete from notification_preferences where user_id = %s", [uid])
        sql(
            "insert into notification_preferences (user_id, event, email, telegram, "
            "created_at, updated_at) values (%s, 'digest', true, false, now(), now()), "
            "(%s, 'moderation', false, true, now() - interval '1 day', "
            "now() - interval '1 day')",
            [uid, uid],
        )

    return подготовить


def _снимок_настроек(uid: int) -> Callable[[], Any]:
    return lambda: sql(
        "select event, email, telegram, updated_at > now() - interval '1 hour' "
        "from notification_preferences where user_id = %s order by event",
        [uid],
    )


@pytest.mark.parametrize(
    ("body", "ожидание"),
    [
        (
            {
                "notifications": [
                    {"event": "digest", "email": False, "telegram": True},
                    {"event": "moderation", "email": False, "telegram": True},
                    {"event": "new_review", "email": True, "telegram": "0"},
                    {"event": "contact_unlocked", "email": 1},
                ]
            },
            # (событие, почта, телеграм, правилась ли строка сейчас):
            # «moderation» не изменилась — updateOrCreate её не трогает
            [
                ("contact_unlocked", True, False, True),
                ("digest", False, True, True),
                ("moderation", False, True, False),
                ("new_review", True, False, True),
            ],
        ),
        (
            {"notifications": {"a": {"event": "digest", "email": "1", "telegram": 0}}},
            [("digest", True, False, True), ("moderation", False, True, False)],
        ),
    ],
)
def test_настройки_сохраняются(сайт, body, ожидание):
    uid = учётка("forms-prefs@savdex.uz")
    итог = отправить(
        сайт,
        "/cabinet/settings/notifications",
        _настройки(uid),
        _снимок_настроек(uid),
        uid=uid,
        body=body,
        method="PATCH",
    )

    # Inertia: PATCH, ответивший переходом, — 303
    assert итог["ответ"]["status"] == 303
    assert '"success":' in итог["сессия"]["payload"]
    assert итог["база"] == ожидание


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"notifications": "x"},
        {"notifications": []},
        {"notifications": [{"event": "nope", "email": "yes"}, {"email": True}, "x"]},
        {"notifications": [{"event": ["digest"], "telegram": None}]},
        {"notifications": [{"event": "  ", "email": 2}]},
    ],
)
@pytest.mark.parametrize("prefix", ["", "/en"])
def test_настройки_с_ошибками(сайт, body, prefix):
    uid = учётка("forms-prefs@savdex.uz")
    итог = отправить(
        сайт,
        f"{prefix}/cabinet/settings/notifications",
        _настройки(uid),
        _снимок_настроек(uid),
        uid=uid,
        body=body,
        method="PATCH",
    )

    assert итог["ответ"]["status"] == 303
    assert '"errors":' in итог["сессия"]["payload"]
    assert '"_old_input":' in итог["сессия"]["payload"]
    # Ничего не сохранено: строки — как до формы
    assert итог["база"] == [("digest", True, False, True), ("moderation", False, True, False)]


# ── Язык ────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    ("path", "referer"),
    [
        ("/locale/uz", "/cabinet/listings?tab=draft"),
        ("/locale/ru", "/en/about"),
        ("/uz/locale/en", "/uz/pricing"),
        ("/locale/tr", "https://evil.example/x"),
    ],
)
@pytest.mark.parametrize("admin", [None, False, True])
def test_смена_языка(сайт, path, referer, admin):
    uid = учётка("forms-locale@savdex.uz", is_admin=bool(admin)) if admin is not None else None

    def подготовить() -> None:
        sql("delete from admin_actions where section = 'users'")

        if uid is not None:
            sql("update users set locale = 'zh' where id = %s", [uid])

    def снимок() -> Any:
        return (
            sql("select locale from users where id = %s", [uid]) if uid else None,
            sql(
                "select user_id, action, section, subject_label, changes::text, ip "
                "from admin_actions where section = 'users' order by id"
            ),
        )

    адрес = referer if referer.startswith("http") else сайт + referer
    итог = отправить(
        сайт,
        path,
        подготовить,
        снимок,
        uid=uid,
        headers={**inertia(), "Referer": адрес},
    )

    assert итог["ответ"]["status"] == 302
    assert bool(итог["база"][1]) is bool(admin)
    assert re.search(r'"locale":"(uz|ru|en|tr)"', итог["сессия"]["payload"])


def test_журнал_администратора_при_языке_из_адреса(сайт):
    """SetLocale у администратора — строка журнала, как AuditObserver (страница Django)."""
    uid = учётка("forms-admin-page@savdex.uz", is_admin=True)
    sql("delete from admin_actions where section = 'users'")
    sql("update users set locale = 'ru' where id = %s", [uid])
    завести(SID, {"_token": ТОКЕН, laravel_session.LOGIN_KEY: uid})

    д = открыть(сайт, "/uz/about", cookies={СЕССИЯ: кука(СЕССИЯ, SID)})
    журнал = sql(
        "select user_id, action, section, subject_label, changes::text, ip "
        "from admin_actions where section = 'users' order by id"
    )

    assert д["status"] == 200
    assert sql("select locale from users where id = %s", [uid]) == [("uz",)]
    assert len(журнал) == 1, журнал
    assert журнал[0][:3] == (uid, "updated", "users"), журнал
    assert '"uz"' in журнал[0][4] and '"ru"' in журнал[0][4], журнал


def test_английские_тексты_ошибок(сайт):
    uid = учётка("forms-prefs@savdex.uz")
    итог = отправить(
        сайт,
        "/en/cabinet/settings/notifications",
        _настройки(uid),
        _снимок_настроек(uid),
        uid=uid,
        body={"notifications": [{"event": "nope", "email": "yes"}]},
        method="PATCH",
    )

    assert "The selected value is invalid." in итог["сессия"]["payload"]
    assert "must be true or false" in итог["сессия"]["payload"]


@pytest.mark.parametrize("inertia_", [True, False])
def test_избранное_частота(inertia_):
    """
    throttle:60,1,favorite на файловом кэше: Inertia — назад с ошибкой,
    иначе 429. Ключ — приставка «favorite» + sha1 номера пользователя.
    """
    import hashlib
    import time

    файловый = {"CACHE_STORE": "file"}
    uid = учётка("forms-throttle@savdex.uz")
    lid = _объявление()
    ключ = "favorite" + hashlib.sha1(str(uid).encode()).hexdigest()

    def подготовить(счёт: int) -> Callable[[], None]:
        def run() -> None:
            _избранное(uid, lid, False)()
            # Счётчик и метка окна — в файловом кэше, как их пишет RateLimiter
            laravel_cache.put(ключ, счёт, 60)
            laravel_cache.put(f"{ключ}:timer", int(time.time()) + 60, 60)

        return run

    try:
        with адрес() as root:
            for счёт, запрет in ((10, False), (60, True)):
                итог = отправить(
                    root,
                    f"/favorites/{lid}",
                    подготовить(счёт),
                    _снимок_избранного(uid, lid),
                    uid=uid,
                    headers=inertia() if inertia_ else {"X-CSRF-TOKEN": ТОКЕН},
                    env=файловый,
                )

                if not запрет:
                    assert итог["ответ"]["status"] == 302
                    assert итог["ответ"]["headers"]["x-ratelimit-remaining"] == "49"
                    assert итог["ответ"]["headers"]["x-ratelimit-limit"] == "60"
                    assert итог["база"]["favorites"] == [(lid,)]
                elif inertia_:
                    assert итог["ответ"]["status"] == 302
                    assert '"error":' in итог["сессия"]["payload"]
                    assert итог["база"]["favorites"] == []
                else:
                    assert итог["ответ"]["status"] == 429
                    assert итог["база"]["favorites"] == []
    finally:
        for имя in (ключ, f"{ключ}:timer"):
            laravel_cache.file_path(имя).unlink(missing_ok=True)
