"""
Предохранители образа: заголовки безопасности Apache, скрытая версия,
пароль администратора не в аргументах, сайт не владельцем базы.
"""

from __future__ import annotations

from .pg_admin import КОРЕНЬ

APACHE = (КОРЕНЬ / "docker/apache-python.conf").read_text()
ЗАПУСК = (КОРЕНЬ / "docker/render-entrypoint.sh").read_text()


def test_заголовки_безопасности():
    for строка in (
        'Header set X-Content-Type-Options "nosniff"',
        'Header set X-Frame-Options "SAMEORIGIN"',
        "Header set Strict-Transport-Security",
    ):
        assert строка in APACHE


def test_загрузки_без_скриптов():
    блок = APACHE[APACHE.index('<Location "/storage/">') :]
    блок = блок[: блок.index("</Location>")]

    assert "sandbox" in блок and "default-src 'none'" in блок


def test_версия_apache_не_видна():
    assert "ServerTokens Prod" in ЗАПУСК and "ServerSignature Off" in ЗАПУСК


def test_пароль_администратора_не_в_аргументах():
    assert '--password "$ADMIN_PASSWORD"' not in ЗАПУСК
    assert "--password-from-env" in ЗАПУСК


def test_боевой_сайт_не_владельцем_базы():
    проверка = '[ -z "${DJANGO_DATABASE_URL:-}" ]'
    assert проверка in ЗАПУСК and "не задан DJANGO_DATABASE_URL" in ЗАПУСК
