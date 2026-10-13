"""
Перевод нейросетью Gemini (savdex/translator.py): с ключом сначала
Gemini, при сбое, лимите или подозрительном ответе — Google Переводчик.

Обе службы — заглушки (HTTP-серверы): Gemini отвечает
«gemini-<язык>:<текст>», Google — «google-<язык>:<текст>». Слово в
тексте выбирает поведение Gemini: LIMIT — 429, BROKEN — 500, LONG —
ответ в разы длиннее текста, CUT — оборванный ответ (MAX_TOKENS).
"""

from __future__ import annotations

import json
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse

import pytest

from savdex import translator

#: Что получила заглушка Gemini: путь, ключ, тело запроса
ЗАПРОСЫ: list[dict[str, Any]] = []


class _Gemini(BaseHTTPRequestHandler):
    def do_POST(self) -> None:
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)))
        ЗАПРОСЫ.append({"path": self.path, "key": self.headers.get("x-goog-api-key"), "body": body})
        text = body["contents"][0]["parts"][0]["text"]
        language = body["systemInstruction"]["parts"][0]["text"]
        code = next(c for c, name in translator.LANGUAGES.items() if f"into {name}." in language)

        if "LIMIT" in text or "BROKEN" in text:
            self.send_response(429 if "LIMIT" in text else 500)
            self.end_headers()

            return

        answer = "x" * 10_000 if "LONG" in text else f"gemini-{code}:{text}"
        reply = {
            "candidates": [
                {
                    "content": {"parts": [{"text": answer + "\n"}]},
                    "finishReason": "MAX_TOKENS" if "CUT" in text else "STOP",
                }
            ]
        }
        self._json(reply)

    def _json(self, data: Any) -> None:
        raw = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args: Any) -> None:
        pass


class _Google(_Gemini):
    def do_POST(self) -> None:
        query = parse_qs(urlparse(self.path).query)
        length = int(self.headers.get("Content-Length") or 0)
        text = parse_qs(self.rfile.read(length).decode()).get("q", [""])[0]
        self._json([[[f"google-{query['tl'][0]}:{text}", text]]])


def _сервер(handler: type[BaseHTTPRequestHandler]) -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()

    try:
        yield f"http://127.0.0.1:{server.server_address[1]}"
    finally:
        server.shutdown()


@pytest.fixture(scope="module")
def gemini() -> Iterator[str]:
    yield from _сервер(_Gemini)


@pytest.fixture(scope="module")
def google() -> Iterator[str]:
    yield from _сервер(_Google)


@pytest.fixture
def окружение(monkeypatch, gemini, google):
    ЗАПРОСЫ.clear()
    monkeypatch.setattr(translator, "_gemini_paused_until", 0.0)
    monkeypatch.setenv("MACHINE_TRANSLATION_ENABLED", "true")
    monkeypatch.setenv("SAVDEX_TRANSLATE_URL", google)
    monkeypatch.setenv("SAVDEX_GEMINI_URL", gemini)
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)

    return monkeypatch


@pytest.mark.parametrize(
    ("язык", "название"),
    [
        ("en", "English"),
        ("uz", "Uzbek (Latin script)"),
        ("zh", "Simplified Chinese"),
        ("tr", "Turkish"),
        ("ru", "Russian"),
    ],
)
def test_gemini_переводит(окружение, язык, название):
    assert translator.Translator().translate("Цемент М400", язык) == f"gemini-{язык}:Цемент М400"

    [запрос] = ЗАПРОСЫ
    assert запрос["path"] == "/models/gemini-flash-lite-latest:generateContent"
    assert запрос["key"] == "test-key"
    assert f"into {название}." in запрос["body"]["systemInstruction"]["parts"][0]["text"]


def test_модель_из_окружения(окружение):
    окружение.setenv("GEMINI_MODEL", "gemini-flash-latest")
    translator.Translator().translate("Цемент", "en")

    assert ЗАПРОСЫ[0]["path"] == "/models/gemini-flash-latest:generateContent"


def test_без_ключа_только_google(окружение):
    окружение.delenv("GEMINI_API_KEY")

    assert translator.Translator().translate("Цемент", "en") == "google-en:Цемент"
    assert ЗАПРОСЫ == []


@pytest.mark.parametrize("слово", ["BROKEN", "LONG", "CUT"])
def test_сбой_gemini_переводит_google(окружение, слово):
    t = translator.Translator()

    assert t.translate(f"Цемент {слово}", "en") == f"google-en:Цемент {слово}"
    assert t.rate_limited is False


def test_лимит_gemini_пауза(окружение):
    t = translator.Translator()

    assert t.translate("Цемент LIMIT", "en") == "google-en:Цемент LIMIT"
    # Лимит кончился — следующие тексты сразу в Google, Gemini не дёргается
    assert t.translate("Кирпич", "en") == "google-en:Кирпич"
    assert len(ЗАПРОСЫ) == 1


def test_длинный_текст_кусками(окружение):
    абзац = "Цемент. " * 400
    text = f"{абзац}\n\n{абзац}"

    результат = translator.Translator().translate(text, "en")

    assert len(ЗАПРОСЫ) == len(translator.chunks(text)) > 1
    assert результат is not None and результат.startswith("gemini-en:")
