"""
ТЗ-03: Google Analytics 4 — тег, события продукта и product_events.

Без базы: когда тег ставится, письменность запроса. С базой: тег и
события в странице (поиск, карточка объявления) только при заданном
GA4_MEASUREMENT_ID; product_events пишет событие оплаты, а задача
отправляет его в GA4 как purchase — в долларах, один раз (подставной
Measurement Protocol на локальном порту).

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL) для проверок с базой.
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, ClassVar

import pytest

from savdex.web import analytics

from .factories import компания, объявление
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, нужна_база, свежая_база
from .test_web_home import справочники
from .web_site import адрес, открыть, страница

GA = {"GA4_MEASUREMENT_ID": "G-TEST1234"}


# ── Без базы ────────────────────────────────────────────────────────


def test_тег_только_на_боевом(monkeypatch):
    monkeypatch.delenv("GA4_MEASUREMENT_ID", raising=False)
    monkeypatch.setenv("APP_ENV", "local")
    assert analytics.measurement_id() == ""
    assert analytics.head_tags("/") == []

    monkeypatch.setenv("APP_ENV", "production")
    assert analytics.measurement_id() == analytics.DEFAULT_ID
    теги = analytics.head_tags("/catalog")
    assert "gtag/js?id=G-E5YEXDTG4X" in теги[0]
    assert "send_page_view:false" in теги[1]
    # Админка тег не отправляет
    assert analytics.head_tags("/admin/companies") == []

    # Явный номер — и на локальном; мусор вместо номера — тега нет
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("GA4_MEASUREMENT_ID", "G-TEST1234")
    assert analytics.measurement_id() == "G-TEST1234"
    monkeypatch.setenv("GA4_MEASUREMENT_ID", "<script>")
    assert analytics.measurement_id() == ""


@pytest.mark.parametrize(
    ("q", "script"),
    [("", "none"), ("цемент", "cyrillic"), ("cement", "latin"), ("水泥", "cjk"), ("500", "other")],
)
def test_письменность_запроса(q, script):
    assert analytics.script_of(q) == script


# ── С базой: страница ───────────────────────────────────────────────


@pytest.fixture(scope="module")
def сайт() -> Iterator[dict[str, Any]]:
    свежая_база()
    справочники()
    c = компания(name="ООО «Цемент-Сервис»")
    lid = объявление(company_id=c, title="Цемент М500", slug="cement-m500")

    with адрес() as root:
        yield {"root": root, "listing": lid}


@нужна_база
def test_без_номера_тега_нет(сайт):
    д = открыть(сайт["root"], "/")

    assert "googletagmanager" not in д["body"]
    assert страница(д["body"])["props"]["analytics"] == {"id": "", "plan": None, "events": []}


@нужна_база
def test_тег_и_события_страницы(сайт):
    д = открыть(сайт["root"], "/", env=GA)
    assert "googletagmanager.com/gtag/js?id=G-TEST1234" in д["body"]
    props = страница(д["body"])["props"]["analytics"]
    assert props["id"] == "G-TEST1234" and props["plan"] is None and props["events"] == []

    поиск = страница(
        открыть(сайт["root"], "/catalog?q=%D1%86%D0%B5%D0%BC%D0%B5%D0%BD%D1%82", env=GA)["body"]
    )["props"]["analytics"]["events"]
    assert поиск == [
        {
            "name": "search_performed",
            "params": {
                "q_script": "cyrillic",
                "type": "all",
                "results_count": 1,
                "has_filters": False,
            },
        }
    ]

    # Просто каталог без запроса и фильтров — не поиск
    assert not страница(открыть(сайт["root"], "/catalog", env=GA)["body"])["props"]["analytics"][
        "events"
    ]

    карточка = страница(открыть(сайт["root"], "/listing/cement-m500", env=GA)["body"])["props"]
    assert карточка["analytics"]["events"] == [
        {
            "name": "listing_viewed",
            "params": {"listing_id": сайт["listing"], "type": "supply", "is_platform": False},
        }
    ]


# ── С базой: product_events и покупка в GA4 ─────────────────────────


class _MP(BaseHTTPRequestHandler):
    received: ClassVar[list[dict[str, Any]]] = []

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        _MP.received.append(
            {"path": self.path, "body": json.loads(self.rfile.read(length) or b"{}")}
        )
        self.send_response(204)
        self.end_headers()

    def log_message(self, *args: Any) -> None:
        pass


def _python(code: str, **env: str) -> str:
    out = subprocess.run(
        [sys.executable, "manage.py", "shell", "-c", code],
        cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "PYTHONPATH": str(PYTHON), "NO_PROXY": "127.0.0.1", **env},
        capture_output=True,
        text=True,
        check=True,
    )

    return out.stdout


@нужна_база
def test_оплата_уходит_в_ga4_один_раз(сайт):
    sql("truncate product_events restart identity")
    сервер = HTTPServer(("127.0.0.1", 0), _MP)
    threading.Thread(target=сервер.serve_forever, daemon=True).start()
    _MP.received.clear()
    окружение = {
        "GA4_API_SECRET": "secret",
        "GA4_MEASUREMENT_ID": "G-TEST1234",
        "GA4_MP_URL": f"http://127.0.0.1:{сервер.server_port}/mp/collect",
    }

    try:
        # Без секрета — ничего не уходит
        _python(
            "from savdex import product_events as p;"
            "p.record('payment_succeeded', company_id=7, plan='pro', props={'number': 'SX-1',"
            "'amount': 1265000, 'currency': 'UZS', 'purpose': 'subscription'});"
            "print(p.send_purchases())",
            GA4_API_SECRET="",
        )
        assert _MP.received == []

        вывод = _python(
            "from savdex import product_events as p; print(p.send_purchases())", **окружение
        )
        assert "отправлено 1 из 1" in вывод

        [запрос] = _MP.received
        assert (
            "measurement_id=G-TEST1234" in запрос["path"] and "api_secret=secret" in запрос["path"]
        )
        [покупка] = запрос["body"]["events"]
        assert покупка["name"] == "purchase"
        assert покупка["params"]["transaction_id"] == "SX-1"
        assert покупка["params"]["currency"] == "USD"
        assert покупка["params"]["value"] > 0
        assert запрос["body"]["client_id"] == "company.7"

        # Повтор не шлёт ту же покупку второй раз
        assert "отправлено 0 из 0" in _python(
            "from savdex import product_events as p; print(p.send_purchases())", **окружение
        )
        [(событие, тариф, отправлено)] = sql(
            "select event, plan, ga_sent_at is not null from product_events"
        )
        assert (событие, тариф, отправлено) == ("payment_succeeded", "pro", True)
    finally:
        сервер.shutdown()
