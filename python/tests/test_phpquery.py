"""
Строка запроса, как у Laravel: сверка с настоящим Symfony.

Request::normalizeQueryString запускается в PHP на тех же строках —
разбор parse_str, ksort и http_build_query у Python обязаны дать
ровно тот же результат. Нужен только PHP (без базы).
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from savdex.web.phpquery import build_query, full_path, laravel_input, normalize

from .pg_admin import КОРЕНЬ

СЛУЧАИ = [
    "type=platform&page=2",
    "b=1&a=2&a=3",
    "a=%20x&a=y+z",
    "q=цемент+м400&page=1",
    "a[]=1&a[]=2&b[x]=3&b[y][]=4",
    "a[b=1",
    "a[b]c=1&a[d]=2",
    "a=1&a[]=2",
    "a[]=2&a=1",
    "=1&&x=&y",
    "10=a&9=b&x=c&01=d&-1=e",
    "%E2%80%A6=1&%FF=2",
    "a%5Bb%5D=1",
    "  lead=1&a.b=2&c d=3",
    "a[0]=x&a[5]=y&a[]=z",
    "k=~tilde_-.",
    "u=%C3%A9%2F%3F%26",
]

PHP = (
    "require 'vendor/autoload.php';"
    "echo json_encode(array_map(fn ($q) => "
    "Symfony\\Component\\HttpFoundation\\Request::normalizeQueryString($q), "
    "json_decode($argv[1], true)));"
)


@pytest.mark.skipif(shutil.which("php") is None, reason="нужен PHP")
def test_как_у_symfony():
    вывод = subprocess.run(
        ["php", "-r", PHP, json.dumps(СЛУЧАИ)],
        cwd=КОРЕНЬ,
        capture_output=True,
        text=True,
        check=True,
    )
    expected = json.loads(вывод.stdout)

    assert [normalize(q) for q in СЛУЧАИ] == expected


def test_путь_как_в_full_url():
    assert full_path("/", "") == ""
    assert full_path("/", "b=1&a=2") == "/?a=2&b=1"
    assert full_path("/reviews/", "type=platform&page=2") == "/reviews?page=2&type=platform"


#: Для laravel_input: пробелы Юникода, невидимые знаки, пустые, пароль
ВВОД = [
    *СЛУЧАИ,
    "q=%20%20Excel%C2%A0&e=&page=%202%20",
    "q=%E2%80%8B%D1%86%D0%B5%D0%BC%D0%B5%D0%BD%D1%82%E3%80%80",
    "a[]=%20x&a[]=&b[c]=%09y%0A",
    "password=%20p%20&current_password=%20&name=%20",
    "bad=%FF%20&ok=%20%20",
    # имена, которые parse_str самого PHP портит, а Symfony — нет
    "a[b.c d=1&x[=2&a.b[c.d]=3&[z]=4&a]b=5&a.b[=6",
]

PHP_ВВОД = (
    "require 'vendor/autoload.php';"
    "use Illuminate\\Foundation\\Http\\Middleware as M;"
    "echo json_encode(array_map(function ($q) {"
    " $r = Illuminate\\Http\\Request::create('/x?'.$q);"
    " (new M\\TrimStrings)->handle($r, fn ($r) => $r);"
    " (new M\\ConvertEmptyStringsToNull)->handle($r, fn ($r) => $r);"
    " $nulls = array_keys(array_filter($r->query(), 'is_null'));"
    " return [Illuminate\\Support\\Arr::query($r->query()), array_map('strval', $nulls)];"
    "}, json_decode($argv[1], true)));"
)


@pytest.mark.skipif(shutil.which("php") is None, reason="нужен PHP")
def test_ввод_после_trim_strings():
    вывод = subprocess.run(
        ["php", "-r", PHP_ВВОД, json.dumps(ВВОД)],
        cwd=КОРЕНЬ,
        capture_output=True,
        text=True,
        check=True,
    )
    expected = json.loads(вывод.stdout)
    got = []

    for q in ВВОД:
        data = laravel_input(q)
        got.append([build_query(data), [str(k) for k, v in data.items() if v is None]])

    assert got == expected
