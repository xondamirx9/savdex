"""
Вход не выдаёт по времени ответа, есть ли такая почта: без учётки
сверок bcrypt столько же, сколько при неверном пароле настоящей.
Без базы — поиск учётки и сверка подменены.
"""

from __future__ import annotations

from typing import Any

import pytest

from savdex.web import guard

ПАРОЛЬ = "Savdex2026!"


@pytest.fixture
def сверки(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Хеши, с которыми сверялся пароль, по порядку."""
    вызовы: list[str] = []

    def check(password: str, hashed: str | None) -> bool:
        вызовы.append(hashed or "")

        return False

    monkeypatch.setenv("BCRYPT_ROUNDS", "4")
    monkeypatch.setattr(guard, "check", check)

    return вызовы


def _учётка(есть: bool, monkeypatch: pytest.MonkeyPatch) -> None:
    user = {"id": 1, "password": guard.hash_password("другой", 4)} if есть else None

    monkeypatch.setattr(guard, "user_by_email", lambda email: user)
    monkeypatch.setattr(guard, "_rows", lambda sql, params: [user] if user else [])


def _вход(ctx: Any = None) -> None:
    assert guard.attempt(ctx, "a@b.uz", ПАРОЛЬ) is None
    assert guard.attempt_forgiving(ctx, "a@b.uz", ПАРОЛЬ) is None


@pytest.mark.parametrize("есть", [True, False])
def test_сверок_столько_же(сверки, monkeypatch, есть):
    _учётка(есть, monkeypatch)
    _вход()

    # attempt — одна сверка, attempt_forgiving — по варианту набора
    assert len(сверки) == 1 + len(guard.keyboard_variants(ПАРОЛЬ))
    # Без учётки — с хешем той же стоимости, что у настоящих
    assert all(h.startswith("$2y$04$") for h in сверки)


def test_пустой_пароль_учётки_тоже_сверяется(сверки, monkeypatch):
    """Учётка без пароля (вход только по SMS) — время то же, что у прочих."""
    monkeypatch.setattr(guard, "user_by_email", lambda email: {"id": 1, "password": ""})
    monkeypatch.setattr(guard, "_rows", lambda sql, params: [{"id": 1, "password": ""}])
    _вход()

    assert len(сверки) == 1 + len(guard.keyboard_variants(ПАРОЛЬ))
