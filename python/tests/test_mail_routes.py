"""
Почтовик для китайских ящиков (savdex/web/mail.py: CN_MAIL_*) и адреса-
заглушки, на которые письма не шлются. База не нужна.
"""

from __future__ import annotations

from savdex.web import mail


def test_китайские_ящики():
    assert mail.is_chinese_mailbox("Wang@QQ.com")
    assert mail.is_chinese_mailbox("li@163.com")
    assert not mail.is_chinese_mailbox("aziz@gmail.com")


def test_маршрут_письма(monkeypatch):
    monkeypatch.delenv("CN_MAIL_MAILER", raising=False)
    # Свой почтовик не задан — как раньше, через обычный
    assert mail._routes("wang@qq.com", "MAIL") == ["MAIL"]

    monkeypatch.setenv("CN_MAIL_MAILER", "smtp")
    # Задан — на китайский ящик сначала он, при сбое — обычный
    assert mail._routes("wang@qq.com", "MAIL") == ["CN_MAIL", "MAIL"]
    assert mail._routes("aziz@gmail.com", "MAIL") == ["MAIL"]
    # Рассылке продаж — свой почтовик всегда
    assert mail._routes("wang@qq.com", "PROSPECT_MAIL") == ["PROSPECT_MAIL"]


def test_адреса_заглушки():
    # Зоны RFC 2606 — почта туда не доходит никогда
    assert mail.undeliverable("demo-1@demo.savdex.test")
    assert mail.undeliverable("a@b.EXAMPLE")
    assert mail.undeliverable("x@host.invalid.")
    assert mail.undeliverable("x@localhost")
    # Настоящие и похожие на них — шлются
    assert not mail.undeliverable("aziz@gmail.com")
    assert not mail.undeliverable("user1@example.com")
    assert not mail.undeliverable("x@test.uz")
    assert not mail.undeliverable("x@contest.uz")


def test_на_заглушку_через_smtp_не_шлётся(monkeypatch):
    monkeypatch.setenv("MAIL_MAILER", "smtp")
    # Почтовика нет: попытка отправить упала бы
    monkeypatch.setenv("MAIL_HOST", "127.0.0.1")
    monkeypatch.setenv("MAIL_PORT", "9")
    monkeypatch.setenv("MAIL_TIMEOUT", "2")

    assert mail.send("demo-1@demo.savdex.test", "Тема", "<p>x</p>", "x")
    assert not mail.send("aziz@gmail.com", "Тема", "<p>x</p>", "x")
