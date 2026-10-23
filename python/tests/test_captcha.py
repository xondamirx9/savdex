"""
Капча регистрации (savdex/web/captcha.py): разбор ответа, одноразовость
задания и пропуска, срок, картинка; на PostgreSQL — выдача картинки,
окно «Я не робот», первый шаг регистрации с пропуском и вход без капчи.
"""

from __future__ import annotations

import io
import json
import time
from typing import Any

import pytest
from PIL import Image

from savdex.web import captcha
from savdex.web.session import Store

from .factories import узбекистан
from .pg_admin import sql, нужна_база, свежая_база
from .test_web_auth_actions import ВЕРНО, вход, сброс
from .test_web_forms import SID, ТОКЕН, inertia, отправить
from .test_web_register_actions import ОКРУЖЕНИЕ_ПОЧТЫ
from .test_web_register_code import ОКРУЖЕНИЕ_DJANGO
from .test_web_session import СЕССИЯ, завести, кука, строка
from .web_site import адрес, открыть


@pytest.fixture(autouse=True)
def _капча(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAPTCHA_ENABLED", "true")


def задание(answer: str = "K7MPX", через: int = 600) -> Store:
    store = Store(id="x" * 40)
    store.put("captcha.register", {"answer": answer, "expires": int(time.time()) + через})

    return store


@pytest.mark.parametrize(
    ("ответ", "итог"),
    [
        ("K7MPX", None),
        ("k7mpx", None),
        (" K7 MPX ", None),
        ("K7MP", "wrong"),
        ("K7MPXX", "wrong"),
        ("K7MPY", "wrong"),
        (["K7MPX"], "required"),
        (12345, "required"),
        ("", "required"),
        ("   ", "required"),
        (None, "required"),
    ],
)
def test_проверка_ответа(ответ: Any, итог: str | None) -> None:
    assert captcha.verify(задание(), "register", ответ) == итог


def test_задание_одноразовое() -> None:
    store = задание()

    assert captcha.verify(store, "register", "AAAAA") == "wrong"
    # Верный ответ после неверного уже не проходит: задание погашено
    assert captcha.verify(store, "register", "K7MPX") == "expired"


def test_верный_ответ_тоже_гасит_задание() -> None:
    store = задание()

    assert captcha.verify(store, "register", "K7MPX") is None
    assert captcha.verify(store, "register", "K7MPX") == "expired"


def test_просроченное_задание() -> None:
    assert captcha.verify(задание(через=-1), "register", "K7MPX") == "expired"


def test_задание_другой_формы_не_подходит() -> None:
    assert captcha.verify(задание(), "login", "K7MPX") == "expired"


def test_выключенная_капча_пропускает(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAPTCHA_ENABLED", "false")

    assert captcha.verify(Store(id="x" * 40), "register", None) is None


def пропуск(token: str = "pass-1", через: int = 600) -> Store:
    store = Store(id="x" * 40)
    store.put("captcha_pass.register", {"token": token, "expires": int(time.time()) + через})

    return store


@pytest.mark.parametrize(
    ("store", "ответ", "итог"),
    [
        (пропуск, "pass-1", None),
        (пропуск, "pass-2", "confirm_expired"),
        (пропуск, "", "not_confirmed"),
        (пропуск, None, "not_confirmed"),
        (пропуск, ["pass-1"], "not_confirmed"),
        (lambda: пропуск(через=-1), "pass-1", "confirm_expired"),
        (lambda: Store(id="x" * 40), "pass-1", "confirm_expired"),
    ],
)
def test_пропуск_формы(store: Any, ответ: Any, итог: str | None) -> None:
    assert captcha.confirm(store(), "register", ответ) == итог


def test_пропуск_одноразовый() -> None:
    store = пропуск()

    assert captcha.confirm(store, "register", "pass-1") is None
    assert captcha.confirm(store, "register", "pass-1") == "confirm_expired"


def test_пропуск_другой_формы_не_подходит() -> None:
    assert captcha.confirm(пропуск(), "login", "pass-1") == "confirm_expired"


def test_код() -> None:
    codes = {captcha.code() for _ in range(200)}

    assert all(len(c) == captcha.LENGTH and set(c) <= set(captcha.ALPHABET) for c in codes)
    # Похожих знаков в наборе нет
    assert not set("0O1IL") & set(captcha.ALPHABET)
    assert len(codes) > 190


def test_картинка() -> None:
    first, second = captcha.render("K7MPX"), captcha.render("K7MPX")

    with Image.open(io.BytesIO(first)) as image:
        assert (image.format, image.size) == ("PNG", (captcha.WIDTH, captcha.HEIGHT))

    # Один и тот же код рисуется каждый раз по-новому
    assert first != second


# ── На PostgreSQL: картинка, окно «Я не робот», регистрация, вход ──

#: Запросы идут в отдельный процесс с окружением tests/pg_admin.ОКРУЖЕНИЕ,
#: где капча выключена, — включаем её для каждого запроса
КАПЧА = {"CAPTCHA_ENABLED": "true"}
JSON = {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"}


@pytest.fixture(scope="module")
def сайт() -> Any:
    свежая_база()
    узбекистан()

    with адрес(**ОКРУЖЕНИЕ_ПОЧТЫ) as root:
        yield root


@нужна_база
def test_выдача_картинки(сайт: str) -> None:
    завести(SID, {"_token": ТОКЕН})
    ответ = открыть(сайт, "/captcha?for=register", {СЕССИЯ: кука(СЕССИЯ, SID)}, JSON, env=КАПЧА)
    data = json.loads(ответ["body"])
    payload = json.loads(строка(SID)["payload"])
    answer = payload["captcha"]["register"]["answer"]

    assert ответ["status"] == 200
    assert data["image"].startswith("data:image/png;base64,")
    assert data["length"] == captcha.LENGTH == len(answer)
    # Код — только в сессии, не в ответе
    assert answer not in ответ["body"] and set(data) == {"image", "length"}
    # Запрос скрипта не становится «предыдущей страницей» для back()
    assert "captcha" not in str(payload.get("_previous", {}).get("url", ""))


@нужна_база
@pytest.mark.parametrize("purpose", ["admin", ""])
def test_картинка_только_для_регистрации_и_входа(сайт: str, purpose: str) -> None:
    assert открыть(сайт, f"/captcha?for={purpose}", env=КАПЧА)["status"] == 404


def _окно(сайт: str, введено: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """POST /captcha/verify с картинкой K7MPX в сессии: ответ и сессия после него."""
    завести(
        SID,
        {
            "_token": ТОКЕН,
            "captcha": {"register": {"answer": "K7MPX", "expires": int(time.time()) + 600}},
        },
    )
    ответ = открыть(
        сайт,
        "/captcha/verify?for=register",
        {СЕССИЯ: кука(СЕССИЯ, SID)},
        # Токен открытым текстом — X-CSRF-TOKEN; X-XSRF-TOKEN браузер шлёт
        # зашифрованным, прямо из куки (forms._token_from_request)
        {**JSON, "X-CSRF-TOKEN": ТОКЕН},
        env=КАПЧА,
        method="POST",
        body=json.dumps({"captcha": введено}),
        content_type="application/json",
    )

    return ответ, json.loads(строка(SID)["payload"])


@нужна_база
def test_окно_верный_код_даёт_пропуск(сайт: str) -> None:
    ответ, payload = _окно(сайт, "k7 mpx")
    data = json.loads(ответ["body"])

    assert ответ["status"] == 200
    assert payload["captcha_pass"]["register"]["token"] == data["token"]
    # Картинка погашена
    assert "register" not in payload.get("captcha", {})


@нужна_база
@pytest.mark.parametrize(("введено", "ошибка"), [("K7MPY", "wrong"), ("", "required")])
def test_окно_неверный_код(сайт: str, введено: str, ошибка: str) -> None:
    ответ, payload = _окно(сайт, введено)

    assert ответ["status"] == 422
    assert json.loads(ответ["body"])["error"] == ошибка
    assert "captcha_pass" not in payload
    assert "register" not in payload.get("captcha", {})


@нужна_база
def test_окно_без_токена_csrf(сайт: str) -> None:
    завести(SID, {"_token": ТОКЕН})
    ответ = открыть(
        сайт,
        "/captcha/verify?for=register",
        {СЕССИЯ: кука(СЕССИЯ, SID)},
        {"Accept": "application/json"},
        env=КАПЧА,
        method="POST",
        body=json.dumps({"captcha": "K7MPX"}),
        content_type="application/json",
    )

    assert ответ["status"] == 419


@нужна_база
@pytest.mark.parametrize(
    ("пропуск_формы", "дальше"),
    [("pass-1", True), ("pass-2", False), ("", False)],
)
def test_регистрация_с_капчей(сайт: str, пропуск_формы: str, дальше: bool) -> None:
    [(country_id,)] = sql("select id from countries where code = 'uz'")
    итог = отправить(
        сайт,
        "/register/email",
        lambda: None,
        body={"country_id": country_id, "email": "robot@reg.savdex.uz", "captcha": пропуск_формы},
        данные={
            "captcha_pass": {"register": {"token": "pass-1", "expires": int(time.time()) + 600}}
        },
        env={**ОКРУЖЕНИЕ_DJANGO, **КАПЧА},
        headers=inertia(Referer=сайт + "/register"),
    )
    location = итог["ответ"]["headers"]["location"]
    payload = json.loads(итог["сессия"]["payload"])

    if дальше:
        assert location.endswith("/register/code")
    else:
        # Без пропуска письмо не уходит: остаёмся на первом шаге
        assert location.endswith("/register")
        assert list(payload["errors"]["default"]["messages"]) == ["captcha"]
        assert "email" not in payload.get("register", {})

    # Пропуск одноразовый
    assert "captcha_pass" not in payload or not payload["captcha_pass"]


@нужна_база
def test_вход_без_капчи(сайт: str) -> None:
    """Капча включена, но вход её не спрашивает, пока учётку не перебирают."""
    итог = вход(сайт, "/login", сброс(), body=ВЕРНО, env=КАПЧА)

    assert итог["status"] == 302
    assert итог["location"] == f"{сайт}/cabinet"
