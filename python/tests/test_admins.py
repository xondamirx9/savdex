"""
Выдача доступа в админку: правила, которые команда применяет молча.

Расхождение здесь — это администратор, который не может войти, или
адрес, который команда принимает, а форма входа нет. Ожидания записаны
явно: проверка почты — как filter_var(FILTER_VALIDATE_EMAIL),
нормализация — trim и нижний регистр, роли — в порядке подсказки.

База не нужна.
"""

from __future__ import annotations

import bcrypt
import pytest

from savdex import admins
from savdex.management.commands.admin import _filled, _url
from savdex.web import guard

# Адреса, на которых правила проверки почты легко ошибиться, и ответ
АДРЕСА = [
    ("boss@savdex.uz", True),
    ("Boss@Savdex.UZ", True),
    ("a@b.c", True),
    # Домен без точки — нет
    ("a@b", False),
    ("a@localhost", False),
    ("user.name+tag@example.co.uk", True),
    # Точки: две подряд, в начале или в конце имени — нет
    ("a..b@example.com", False),
    (".a@example.com", False),
    ("a.@example.com", False),
    # Дефис по краям части домена и подчёркивание — нет
    ("a@-example.com", False),
    ("a@example-.com", False),
    ("a@exa_mple.com", False),
    ("a@xn--80ak6aa92e.com", True),
    ("a@123.com", True),
    # Верхний уровень из одних цифр — нет, с буквой — да
    ("a@example.123", False),
    ("a@[127.0.0.1]", True),
    ("a@[256.0.0.1]", False),
    ("a@[IPv6:::1]", True),
    # Кавычки: без пробела и с экранированной кавычкой — да
    ('"x y"@example.com', False),
    ('"xy"@example.com', True),
    ('"x\\"y"@example.com', True),
    ("x@@example.com", False),
    ("@example.com", False),
    ("example.com", False),
    # Не ASCII — нет (без FILTER_FLAG_EMAIL_UNICODE)
    ("не-почта", False),
    ("почта@пример.рф", False),
    ("user@пример.рф", False),
    ("üser@example.com", False),
    # Пробелы и управляющие знаки — нет, даже в конце
    ("a b@example.com", False),
    ("a@example.com ", False),
    ("a@example.com\n", False),
    ("a\x00@example.com", False),
    ("a!#$%&'*+/=?^_`{|}~-@example.com", True),
    # Имя до 64 знаков, часть домена до 63, весь адрес до 320
    ("a" * 64 + "@example.com", True),
    ("a" * 65 + "@example.com", False),
    ("a@" + "b" * 63 + ".com", True),
    ("a@" + "b" * 64 + ".com", False),
    ("a@" + ".".join(["b" * 60] * 5) + ".com", False),
    ("a@" + "b" * 320, False),
    ("", False),
    ("A@EXAMPLE.COM", True),
    ("a@e.co", True),
    ("a@e.c0", True),
    ("a@e.xn--p1ai", True),
    ("a@e..com", False),
]


class TestПочта:
    @pytest.mark.parametrize(("адрес", "годен"), АДРЕСА)
    def test_проверка_как_filter_var(self, адрес, годен):
        assert admins.valid_email(адрес) is годен

    def test_проверка_различает(self):
        """Проверка слепа, если все адреса дают одно и то же."""
        итоги = {admins.valid_email(адрес) for адрес, _ in АДРЕСА}

        assert итоги == {True, False}

    @pytest.mark.parametrize(
        ("адрес", "итог"),
        [
            ("Boss@Savdex.UZ", "boss@savdex.uz"),
            ("  Boss@Savdex.UZ\t", "boss@savdex.uz"),
            (" boss@savdex.uz", "boss@savdex.uz"),
            ("a@example.com ", "a@example.com"),
            ("a@example.com\n", "a@example.com"),
            # trim у PHP снимает и \0, и \x0B — но только по краям
            ("\x0bA@b.cz\r\n", "a@b.cz"),
            ("\x00a@b.cz\x00", "a@b.cz"),
            ("a\x00@example.com", "a\x00@example.com"),
            # mb_strtolower — и не ASCII
            ("ÄDMIN@x.uz", "ädmin@x.uz"),
            ("ПОЧТА@Пример.РФ", "почта@пример.рф"),
            ("", ""),
        ],
    )
    def test_нормализация_trim_и_нижний_регистр(self, адрес, итог):
        """mb_strtolower(trim($e)): пробелы по краям прочь, всё — строчными."""
        assert admins.normalize_email(адрес) == итог


class TestРоли:
    def test_роли_и_названия(self):
        # Порядок тоже: он печатается в подсказке при неизвестной роли
        assert list(admins.ROLES.items()) == [
            ("superadmin", "Суперадмин"),
            ("admin", "Администратор"),
            ("sales", "Отдел продаж"),
            ("supplier_manager", "Менеджер поставщиков"),
            ("buyer_manager", "Менеджер покупателей"),
            ("moderator", "Модератор"),
            ("finance", "Финансы"),
            ("support", "Поддержка"),
            ("content_manager", "Контент-менеджер"),
        ]


class TestПароль:
    def test_длина_и_состав(self):
        for _ in range(200):
            пароль = admins.generate_password()

            assert len(пароль) == 14
            assert пароль.isalnum() and пароль.isascii()
            assert any(c.isalpha() for c in пароль), "хотя бы одна буква, как у Laravel"
            assert any(c.isdigit() for c in пароль), "хотя бы одна цифра, как у Laravel"

    def test_пароли_не_повторяются(self):
        assert len({admins.generate_password() for _ in range(200)}) == 200

    def test_хеш_с_префиксом_2y(self):
        хеш = admins.hash_password("Savdex2026!x", rounds=4)

        assert хеш.startswith("$2y$04$")
        assert bcrypt.checkpw(b"Savdex2026!x", хеш.replace("$2y$", "$2b$", 1).encode())

    def test_длинный_пароль_обрезается_до_72_байт(self):
        хеш = admins.hash_password("a" * 100, rounds=4).replace("$2y$", "$2b$", 1).encode()

        assert bcrypt.checkpw(b"a" * 72, хеш)

    def test_вход_принимает_хеш(self):
        """
        Главная проверка переноса хеширования: хеш команды (`$2y$`, как у
        PHP) принимает проверка пароля при входе на сайт (guard.check).
        """
        пароли = ["Savdex2026!x", "пароль-кириллицей", "a" * 100, "0"]

        for пароль in пароли:
            хеш = admins.hash_password(пароль, rounds=4)

            assert хеш.startswith("$2y$04$") and len(хеш) == 60
            assert guard.check(пароль, хеш), пароль
            assert not guard.check(пароль + "x", хеш) or len(пароль.encode()) >= 72, пароль

        assert not guard.check("Savdex2026!x", admins.hash_password("другой", rounds=4))


class TestПараметры:
    @pytest.mark.parametrize(
        ("значение", "ожидается"),
        [("", ""), ("0", ""), ("00", "00"), ("finance", "finance"), (" ", " ")],
    )
    def test_пустое_и_ноль_значат_не_задано(self, значение, ожидается):
        """`--password=0` для PHP — «сгенерировать»: строка «0» ложна."""
        assert _filled(значение) == ожидается


class TestАдресСайта:
    """
    Строка «Адрес» в таблице — куда идти входить.

    На Render APP_URL может быть пуст: сайт при запуске подставляет
    RENDER_EXTERNAL_URL (docker/render-entrypoint.sh), а в Shell этой
    подстановки нет. Команда печатала http://localhost/admin, и
    администратор шёл входить не туда.
    """

    def test_задан_app_url(self, monkeypatch):
        monkeypatch.setenv("APP_URL", "https://savdex.uz/")
        monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://savdex.onrender.com")

        assert _url("/admin") == "https://savdex.uz/admin"

    @pytest.mark.parametrize("пусто", [None, ""])
    def test_пустой_app_url_как_при_запуске_сайта(self, monkeypatch, пусто):
        if пусто is None:
            monkeypatch.delenv("APP_URL", raising=False)
        else:
            monkeypatch.setenv("APP_URL", пусто)

        monkeypatch.setenv("RENDER_EXTERNAL_URL", "https://savdex.onrender.com")

        assert _url("/admin") == "https://savdex.onrender.com/admin"

    def test_вне_render(self, monkeypatch):
        monkeypatch.delenv("APP_URL", raising=False)
        monkeypatch.delenv("RENDER_EXTERNAL_URL", raising=False)

        assert _url("/admin") == "http://localhost/admin"
