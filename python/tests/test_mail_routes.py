"""Почтовик для китайских ящиков (savdex/web/mail.py: CN_MAIL_*). База не нужна."""

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
