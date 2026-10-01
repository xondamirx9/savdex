"""
Правило url (savdex.web.url_rule): шаблон Str::isUrl из Laravel —
что сайт принимает как ссылку, а что нет. Ожидания записаны явно,
с пояснением там, где шаблон ведёт себя неочевидно.
"""

from __future__ import annotations

import random

import pytest

from savdex.web.url_rule import is_url

#: Строка и ожидаемый ответ
СТРОКИ = [
    ("https://savdex.uz", True),
    ("http://savdex.uz/", True),
    ("https://savdex.uz/catalog?type=tender&closed=1#top", True),
    ("https://www.savdex.uz:8080/a/b.html", True),
    # Флаг i: протокол и домен без учёта регистра
    ("HTTPS://SAVDEX.UZ", True),
    # Одноуровневый домен и точка в конце домена допустимы
    ("http://a", True),
    ("http://a.", True),
    ("http://a..b", False),
    # Дефис и подчёркивание в домене шаблон не запрещает
    ("http://-a.uz", True),
    ("http://a_b.uz", True),
    # Буквы любых алфавитов и punycode
    ("https://сайт.рф/путь", True),
    ("https://例子.中国", True),
    ("https://xn--80aswg.xn--p1ai", True),
    ("http://127.0.0.1", True),
    # Октеты не проверяются: цифры подходят и как домен
    ("http://999.999.999.999", True),
    ("http://[::1]", True),
    ("http://[2001:db8::1]:443/x", True),
    ("http://[::1", False),
    ("http://user:pass@savdex.uz", True),
    ("http://user@savdex.uz", True),
    ("http://@savdex.uz", False),
    ("ftp://files.savdex.uz/a.zip", True),
    ("mailto://a@b.uz", True),
    # Без «//» — не ссылка, даже у известного протокола
    ("mailto:a@b.uz", False),
    ("tg://resolve?domain=savdex", True),
    # javascript нет в списке протоколов
    ("javascript:alert(1)", False),
    ("javascript://alert(1)", False),
    ("savdex.uz", False),
    ("www.savdex.uz", False),
    ("//savdex.uz", False),
    ("https://", False),
    ("https:// savdex.uz", False),
    ("https://savdex.uz/a b", False),
    ("https://savdex.uz/%20", True),
    ("https://savdex.uz/%zz", False),
    # Скобки допустимы в запросе, но не в пути
    ("https://savdex.uz/?q=[1]", True),
    ("https://savdex.uz/[1]", False),
    ("https://savdex.uz#a#b", False),
    # Как у PCRE без флага D: «$» пропускает один перевод строки в конце
    ("https://savdex.uz\n", True),
    ("https://savdex.uz\n\n", False),
    ("https://savdex.uz\r\n", False),
    ("\nhttps://savdex.uz", False),
    ("https://savdex.uz:", False),
    ("https://savdex.uz:abc", False),
    ("https://savdex.uz/~user/!$&'()*+,;=:@", True),
    ("https://a.b.c.d.e.f.g.h", True),
    ("https://a.1", True),
    ("https://1.2.3", True),
    ("https://savdex.uz/путь/файл", True),
    # Символы (\pS) разрешены в домене, но не в пути
    ("https://😀.uz", True),
    ("https://a.uz/😀", False),
    ("", False),
    (" ", False),
    ("http", False),
    ("http:", False),
    ("http:/", False),
    ("http://", False),
]


@pytest.mark.parametrize(("строка", "ожидание"), СТРОКИ)
def test_строки(строка, ожидание):
    assert is_url(строка) is ожидание


def test_случайные_строки_не_ломают_правило():
    """Шаблон с захватывающими квантификаторами: мусор — быстрый ответ True/False."""
    случай = random.Random(20260928)
    азбука = [*"hts:/.a-_1@[]?#%2F :я中\n", "http://", "https://", "www."]
    строки = [
        "".join(случай.choice(азбука) for _ in range(случай.randint(1, 16))) for _ in range(3000)
    ]
    ответы = [is_url(s) for s in строки]

    assert all(isinstance(a, bool) for a in ответы)
    assert 0 < sum(ответы) < len(строки)
    assert all(
        s.lower().startswith(("http://", "https://"))
        for s, a in zip(строки, ответы, strict=True)
        if a
    )


def test_не_строка():
    assert not is_url(None)
    assert not is_url(5)
    assert not is_url(["https://savdex.uz"])
