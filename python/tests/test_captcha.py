"""
Капча входа и регистрации (savdex/web/captcha.py): разбор ответа,
одноразовость задания, срок, рисование сетки; на PostgreSQL — выдача
задания и вход с ним.
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

from .pg_admin import нужна_база, свежая_база
from .test_web_auth_actions import ВЕРНО, вход, ошибки, сброс
from .test_web_forms import SID, ТОКЕН
from .test_web_session import СЕССИЯ, завести, кука, строка
from .web_site import адрес, открыть


@pytest.fixture(autouse=True)
def _капча(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAPTCHA_ENABLED", "true")
    monkeypatch.delenv("CAPTCHA_PHOTOS_DIR", raising=False)


def задание(answer: str = "1,4,7", через: int = 600) -> Store:
    store = Store(id="x" * 40)
    store.put("captcha.login", {"answer": answer, "expires": int(time.time()) + через})

    return store


@pytest.mark.parametrize(
    ("ответ", "итог"),
    [
        ([1, 4, 7], None),
        ([7, 1, 4], None),
        (["1", "4", "7"], None),
        ("1,4,7", None),
        ([1, 4], "wrong"),
        ([1, 4, 7, 8], "wrong"),
        ([1, 4, "x"], "wrong"),
        ([True], "wrong"),
        ([], "required"),
        (None, "required"),
    ],
)
def test_проверка_ответа(ответ: Any, итог: str | None) -> None:
    assert captcha.verify(задание(), "login", ответ) == итог


def test_задание_одноразовое() -> None:
    store = задание()

    assert captcha.verify(store, "login", [1, 2]) == "wrong"
    # Верный ответ после неверного уже не проходит: задание погашено
    assert captcha.verify(store, "login", [1, 4, 7]) == "expired"


def test_верный_ответ_тоже_гасит_задание() -> None:
    store = задание()

    assert captcha.verify(store, "login", [1, 4, 7]) is None
    assert captcha.verify(store, "login", [1, 4, 7]) == "expired"


def test_просроченное_задание() -> None:
    assert captcha.verify(задание(через=-1), "login", [1, 4, 7]) == "expired"


def test_задание_другой_формы_не_подходит() -> None:
    assert captcha.verify(задание(), "register", [1, 4, 7]) == "expired"


def test_выключенная_капча_пропускает(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAPTCHA_ENABLED", "false")

    assert captcha.verify(Store(id="x" * 40), "login", None) is None


def test_сетка() -> None:
    target, tiles, answer = captcha.build()

    assert target in captcha.TARGETS
    assert len(tiles) == captcha.GRID**2
    assert captcha.MIN_TARGETS <= len(answer) <= captcha.MAX_TARGETS
    assert answer == sorted(set(answer)) and all(0 <= n < 9 for n in answer)

    for tile in tiles:
        with Image.open(io.BytesIO(tile)) as image:
            assert (image.format, image.size) == ("JPEG", (captcha.TILE, captcha.TILE))

    # Картинки каждый раз новые: одинаковых байтов нет
    assert len(set(tiles)) == len(tiles)


@pytest.mark.parametrize("kind", sorted(captcha.PAINTERS))
def test_каждый_рисунок(kind: str) -> None:
    for _ in range(5):
        assert captcha._paint(kind).size == (captcha.TILE, captcha.TILE)


def test_фотографии(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    """Фотографий хватает — сетка из них; цели — из папки цели."""
    for name, count in (("traffic_light", 4), ("crosswalk", 4), ("storefront", 4), ("other", 9)):
        (tmp_path / name).mkdir()

        for i in range(count):
            # Цвет папки — по нему видно, откуда клетка
            color = {"traffic_light": (250, 0, 0), "other": (0, 0, 250)}.get(name, (0, 250, 0))
            Image.new("RGB", (300, 200), color).save(tmp_path / name / f"{i}.jpg")

    monkeypatch.setenv("CAPTCHA_PHOTOS_DIR", str(tmp_path))
    monkeypatch.setattr(captcha._rnd, "choice", lambda seq: seq[0])
    target, tiles, answer = captcha.build()

    assert target == "traffic_light"

    for i, tile in enumerate(tiles):
        with Image.open(io.BytesIO(tile)) as image:
            r, _, _ = image.convert("RGB").resize((1, 1)).getpixel((0, 0))  # type: ignore[misc]

        assert (r > 150) is (i in answer), i


def test_фотографий_мало_рисуем(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    (tmp_path / "traffic_light").mkdir()
    monkeypatch.setenv("CAPTCHA_PHOTOS_DIR", str(tmp_path))

    assert captcha._photos() is None


# ── На PostgreSQL: выдача задания и вход ────────────────────────────

#: Запросы идут в отдельный процесс с окружением tests/pg_admin.ОКРУЖЕНИЕ,
#: где капча выключена, — включаем её для каждого запроса
КАПЧА = {"CAPTCHA_ENABLED": "true"}


@pytest.fixture(scope="module")
def сайт() -> Any:
    свежая_база()

    with адрес() as root:
        yield root


@нужна_база
def test_выдача_задания(сайт: str) -> None:
    завести(SID, {"_token": ТОКЕН})
    ответ = открыть(
        сайт,
        "/captcha?for=login",
        {СЕССИЯ: кука(СЕССИЯ, SID)},
        {"Accept": "application/json", "X-Requested-With": "XMLHttpRequest"},
        env=КАПЧА,
    )
    data = json.loads(ответ["body"])
    payload = json.loads(строка(SID)["payload"])

    assert ответ["status"] == 200
    assert data["target"] in captcha.TARGETS and len(data["tiles"]) == 9
    assert all(t.startswith("data:image/jpeg;base64,") for t in data["tiles"])
    # Верные клетки — только в сессии, не в ответе
    assert "answer" not in data
    assert set(payload["captcha"]["login"]) == {"answer", "expires"}
    # Запрос скрипта не становится «предыдущей страницей» для back()
    assert "captcha" not in str(payload.get("_previous", {}).get("url", ""))


@нужна_база
def test_выдача_задания_неизвестной_формы(сайт: str) -> None:
    assert открыть(сайт, "/captcha?for=admin", env=КАПЧА)["status"] == 404


@нужна_база
@pytest.mark.parametrize(
    ("отмечено", "вошёл_ли"),
    [([1, 4, 7], True), ([1, 4], False), ([], False)],
)
def test_вход_с_капчей(сайт: str, отмечено: list[int], вошёл_ли: bool) -> None:
    итог = вход(
        сайт,
        "/login",
        сброс(),
        body={**ВЕРНО, "captcha": отмечено},
        payload={"captcha": {"login": {"answer": "1,4,7", "expires": int(time.time()) + 600}}},
        env=КАПЧА,
    )

    assert итог["status"] == 302

    if вошёл_ли:
        assert итог["location"] == f"{сайт}/cabinet"
    else:
        assert итог["location"] == f"{сайт}/login"
        assert list(ошибки(итог)) == ["captcha"]
        # Неверная капча — не неудачный вход: попытка не записана
        assert итог["db"]["attempts"] == []
