"""
Выдача доступа в админку: правила, которые PHP применяет молча.

Каждое сверяется с самим PHP, а не с моим представлением о нём:
команда пишет в базу, и расхождение здесь — это администратор,
который не может войти, или адрес, который одна версия принимает,
а другая нет.

Проверки против PHP нужен только интерпретатор php с vendor/ — база
не нужна. Без php они пропускаются; в CI он есть.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import bcrypt
import pytest

from savdex import admins
from savdex.management.commands.admin import _filled

КОРЕНЬ = Path(__file__).resolve().parents[2]
PHP = shutil.which("php")
есть_php = pytest.mark.skipif(
    PHP is None or not (КОРЕНЬ / "vendor" / "autoload.php").exists(),
    reason="нет php с зависимостями — сверка с PHP невозможна",
)


def _php(code: str, stdin: str = "") -> str:
    assert PHP is not None

    return subprocess.run(
        [PHP, "-r", f'require "vendor/autoload.php"; {code}'],
        cwd=КОРЕНЬ,
        input=stdin,
        capture_output=True,
        text=True,
        check=True,
    ).stdout


# Адреса, на которых правила проверки почты легко разойтись
АДРЕСА = [
    "boss@savdex.uz",
    "Boss@Savdex.UZ",
    "a@b.c",
    "a@b",
    "a@localhost",
    "user.name+tag@example.co.uk",
    "a..b@example.com",
    ".a@example.com",
    "a.@example.com",
    "a@-example.com",
    "a@example-.com",
    "a@exa_mple.com",
    "a@xn--80ak6aa92e.com",
    "a@123.com",
    "a@example.123",
    "a@[127.0.0.1]",
    "a@[256.0.0.1]",
    "a@[IPv6:::1]",
    '"x y"@example.com',
    '"xy"@example.com',
    '"x\\"y"@example.com',
    "x@@example.com",
    "@example.com",
    "example.com",
    "не-почта",
    "почта@пример.рф",
    "user@пример.рф",
    "üser@example.com",
    "a b@example.com",
    "a@example.com ",
    "a@example.com\n",
    "a\x00@example.com",
    "a!#$%&'*+/=?^_`{|}~-@example.com",
    "a" * 64 + "@example.com",
    "a" * 65 + "@example.com",
    "a@" + "b" * 63 + ".com",
    "a@" + "b" * 64 + ".com",
    "a@" + ".".join(["b" * 60] * 5) + ".com",
    "a@" + "b" * 320,
    "",
    "A@EXAMPLE.COM",
    "a@e.co",
    "a@e.c0",
    "a@e.xn--p1ai",
    "a@e..com",
]


class TestПочта:
    @есть_php
    def test_проверка_как_filter_var(self):
        php = json.loads(
            _php(
                "echo json_encode(array_map(fn ($e) => filter_var($e, FILTER_VALIDATE_EMAIL)"
                " !== false, json_decode(stream_get_contents(STDIN))));",
                json.dumps(АДРЕСА),
            )
        )

        python = [admins.valid_email(адрес) for адрес in АДРЕСА]

        assert python == php, [
            (адрес, p, y) for адрес, p, y in zip(АДРЕСА, php, python, strict=True) if p != y
        ]

    def test_проверка_различает(self):
        """Сверка с PHP слепа, если все адреса дают одно и то же."""
        итоги = {admins.valid_email(адрес) for адрес in АДРЕСА}

        assert итоги == {True, False}

    @есть_php
    def test_нормализация_как_php(self):
        адреса = [*АДРЕСА, "  Boss@Savdex.UZ\t", " boss@savdex.uz", "ÄDMIN@x.uz", "\x0bA@b.cz\r\n"]

        php = json.loads(
            _php(
                "echo json_encode(array_map(fn ($e) => mb_strtolower(trim($e)),"
                " json_decode(stream_get_contents(STDIN))), JSON_UNESCAPED_UNICODE);",
                json.dumps(адреса),
            )
        )

        assert [admins.normalize_email(адрес) for адрес in адреса] == php


class TestРоли:
    @есть_php
    def test_роли_и_названия_как_в_php(self):
        php = json.loads(
            _php("echo json_encode(App\\Support\\AdminAccess::ROLES, JSON_UNESCAPED_UNICODE);")
        )

        # Порядок тоже: он печатается в подсказке при неизвестной роли
        assert list(admins.ROLES.items()) == list(php.items())


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

    def test_хеш_с_префиксом_php(self):
        хеш = admins.hash_password("Savdex2026!x", rounds=4)

        assert хеш.startswith("$2y$04$")
        assert bcrypt.checkpw(b"Savdex2026!x", хеш.replace("$2y$", "$2b$", 1).encode())

    def test_длинный_пароль_обрезается_как_в_php(self):
        хеш = admins.hash_password("a" * 100, rounds=4).replace("$2y$", "$2b$", 1).encode()

        assert bcrypt.checkpw(b"a" * 72, хеш)

    @есть_php
    def test_php_принимает_хеш_от_python(self):
        """
        Главная проверка переноса хеширования.

        Хеш `$2b$` от библиотеки Python PHP не узнаёт — Laravel при входе
        бросил бы исключение. Здесь спрашиваем PHP напрямую.
        """
        пароли = ["Savdex2026!x", "пароль-кириллицей", "a" * 100, "0"]
        хеши = [admins.hash_password(p, rounds=4) for p in пароли]

        php = json.loads(
            _php(
                "$in = json_decode(stream_get_contents(STDIN), true);"
                "echo json_encode(array_map(fn ($p, $h) => ["
                "password_verify($p, $h), password_get_info($h)['algoName']],"
                " $in['p'], $in['h']));",
                json.dumps({"p": пароли, "h": хеши}),
            )
        )

        assert php == [[True, "bcrypt"]] * len(пароли)


class TestПараметры:
    @pytest.mark.parametrize(
        ("значение", "ожидается"),
        [("", ""), ("0", ""), ("00", "00"), ("finance", "finance"), (" ", " ")],
    )
    def test_пустое_как_в_php(self, значение, ожидается):
        """`--password=0` для PHP — «сгенерировать»: строка «0» ложна."""
        assert _filled(значение) == ожидается
