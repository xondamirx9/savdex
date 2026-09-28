"""
Правило url на Python совпадает с Str::isUrl у Laravel: те же строки
прогоняются через PHP (один процесс) и через savdex.web.url_rule.
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess

import pytest

from savdex.web.url_rule import is_url

from .pg_admin import КОРЕНЬ

СТРОКИ = [
    "https://savdex.uz",
    "http://savdex.uz/",
    "https://savdex.uz/catalog?type=tender&closed=1#top",
    "https://www.savdex.uz:8080/a/b.html",
    "HTTPS://SAVDEX.UZ",
    "http://a",
    "http://a.",
    "http://a..b",
    "http://-a.uz",
    "http://a_b.uz",
    "https://сайт.рф/путь",
    "https://例子.中国",
    "https://xn--80aswg.xn--p1ai",
    "http://127.0.0.1",
    "http://999.999.999.999",
    "http://[::1]",
    "http://[2001:db8::1]:443/x",
    "http://[::1",
    "http://user:pass@savdex.uz",
    "http://user@savdex.uz",
    "http://@savdex.uz",
    "ftp://files.savdex.uz/a.zip",
    "mailto://a@b.uz",
    "mailto:a@b.uz",
    "tg://resolve?domain=savdex",
    "javascript:alert(1)",
    "javascript://alert(1)",
    "savdex.uz",
    "www.savdex.uz",
    "//savdex.uz",
    "https://",
    "https:// savdex.uz",
    "https://savdex.uz/a b",
    "https://savdex.uz/%20",
    "https://savdex.uz/%zz",
    "https://savdex.uz/?q=[1]",
    "https://savdex.uz/[1]",
    "https://savdex.uz#a#b",
    "https://savdex.uz\n",
    "https://savdex.uz\n\n",
    "https://savdex.uz\r\n",
    "\nhttps://savdex.uz",
    "https://savdex.uz:",
    "https://savdex.uz:abc",
    "https://savdex.uz/~user/!$&'()*+,;=:@",
    "https://a.b.c.d.e.f.g.h",
    "https://a.1",
    "https://1.2.3",
    "https://savdex.uz/путь/файл",
    "https://😀.uz",
    "https://a.uz/😀",
    "",
    " ",
    "http",
    "http:",
    "http:/",
    "http://",
]


def _php(values: list[str]) -> list[bool]:
    код = (
        "require 'vendor/autoload.php';"
        "$in = json_decode(stream_get_contents(STDIN), true);"
        "echo json_encode(array_map(fn ($s) => Illuminate\\Support\\Str::isUrl($s), $in));"
    )
    вывод = subprocess.run(
        ["php", "-r", код],
        cwd=КОРЕНЬ,
        input=json.dumps(values),
        capture_output=True,
        text=True,
        check=True,
    )

    return json.loads(вывод.stdout)


@pytest.mark.skipif(shutil.which("php") is None, reason="нужен PHP")
def test_как_у_laravel():
    случай = random.Random(20260928)
    азбука = [*"hts:/.a-_1@[]?#%2F :я中\n", "http://", "https://", "www."]
    строки = СТРОКИ + [
        "".join(случай.choice(азбука) for _ in range(случай.randint(1, 16))) for _ in range(3000)
    ]
    ожидание = _php(строки)
    расхождения = [(s, e) for s, e in zip(строки, ожидание, strict=True) if is_url(s) is not e]

    assert not расхождения, расхождения[:20]
    assert sum(ожидание) > 20


def test_не_строка():
    assert not is_url(None)
    assert not is_url(5)
    assert not is_url(["https://savdex.uz"])
