"""
Правило email на Python — как validateEmail у Laravel (RFCValidation из
egulias/email-validator; email:rfc,strict — ещё NoRFCWarningsValidation).

Для каждой строки большого набора (АДРЕСА, сочетания ЛЕВЫЕ и ПРАВЫЕ,
случайные, похожие на адрес, длинные метки IDN, каждый знак Юникода)
ответ egulias записан один раз (ВЕРНЫЕ, ВЕРНЫЕ_СТРОГО — по биту на
строку, по порядку набора) и сверяется с savdex.web.email_rfc. Ответ
снят при обработчике ошибок, как у Laravel (HandleExceptions):
предупреждение становится ErrorException, устаревания молчат — без него
иначе вёл бы себя idn_to_ascii с переполненным ответом.
"""

from __future__ import annotations

import base64
import random
import unicodedata
import zlib

from savdex.web.email_rfc import is_valid

АДРЕСА = [
    # Обычные
    "user@savdex.uz",
    "user.name+tag@savdex.uz",
    "USER@SAVDEX.UZ",
    "a@b",
    "a@b.c",
    "a@1.2",
    "a@b.123",
    "1@2",
    "_@_",
    "a_b@c_d.e",
    "a-b@c-d.e",
    "a@b-c",
    "!#$%&'*+/=?^_`{|}~@example.org",
    "a!b@c",
    "a/b@c.d",
    "a=b@c.d",
    "a?b@c.d",
    "a`b@c.d",
    "a'b@c.d",
    "a{b}@c.d",
    "a|b@c.d",
    "a~b@c.d",
    "a#b@c.d",
    "a*b@c.d",
    "a^b@c.d",
    "a$b@c.d",
    "a%b@c.d",
    "a&b@c.d",
    "a¡b@c.d",
    "a¿b@c.d",
    "a@c¡.d",
    "a@c¿.d",
    # Пустое, без «@», несколько «@»
    "",
    "@",
    "@@",
    "a",
    "a@",
    "@b",
    "@b.c",
    "a@@b",
    "a@b@c",
    "a@b.c@d",
    '"a@b"@c.d',
    "a\\@b@c.d",
    # Точки
    ".a@b.c",
    "a.@b.c",
    "a..b@c.d",
    "a.b.c@d.e",
    "a@.b",
    "a@b.",
    "a@b..c",
    "a@b.c.",
    "a@b.c..",
    ".@b",
    "..@b",
    "a@.",
    "a@..",
    # Дефисы
    "a@-b.c",
    "a@b-.c",
    "a@b.-c",
    "a@b.c-",
    "a@b--c.d",
    "a@-",
    "-@b",
    "a-@b",
    "a@b.c-d",
    "a@xn--80aswg.xn--p1ai",
    "a@XN--80ASWG.XN--P1AI",
    # Кавычки
    '"a"@b.c',
    '"a b"@b.c',
    '"a\\"b"@b.c',
    '"a\\\\b"@b.c',
    '"a\\b"@b.c',
    '"a\\ b"@b.c',
    '"a\tb"@b.c',
    '"a\\\tb"@b.c',
    '"a\x00b"@b.c',
    '"a\\\x00b"@b.c',
    '""@b.c',
    '"@b.c',
    'a"@b.c',
    '"a@b.c',
    'a"b"@c.d',
    '"a"b@c.d',
    '"a".b@c.d',
    'a."b"@c.d',
    '"a"."b"@c.d',
    '"a""b"@c.d',
    '"a\\"@b.c',
    '"\\"@b.c',
    '"\\""@b.c',
    '"a(b)"@c.d',
    '"a@b"@c',
    '"a,b"@c.d',
    '"a<b>"@c.d',
    '"a[b]"@c.d',
    '"a:b;"@c.d',
    '" "@c.d',
    '"я"@c.d',
    '"😀"@c.d',
    '"a"\t@c.d',
    '"a" @c.d',
    '1"a"@c.d',
    '"a"1@c.d',
    # Комментарии
    "(c)a@b.c",
    "a(c)@b.c",
    "(c)@b.c",
    "a(c)b@c.d",
    "a(c@b.c",
    "a)c@b.c",
    "a(c))@b.c",
    "a((c))@b.c",
    "a(c(d))@b.c",
    "a()@b.c",
    "a@(c)b.c",
    "a@b(c).d",
    "a@b.c(d)",
    "a@b(c)",
    "a@(c)",
    "a@b(c.d",
    "a@b)c.d",
    "a@(b).(c).d",
    "a@b(c)(d).e",
    "a@b(c\\)d).e",
    "a(\\ )@b.c",
    "a(\\\t)@b.c",
    "a(a@b)@b.c",
    "(a@b.c",
    "a@b.c)",
    # Пробелы, табуляция, CRLF
    " a@b.c",
    "a @b.c",
    "a@ b.c",
    "a@b.c ",
    "a@b .c",
    "a@b. c",
    "a b@c.d",
    "a\t@b.c",
    "a@\tb.c",
    "\ta@b.c",
    "a@b.c\t",
    "a \t@b.c",
    "a@b\r\n c",
    "a\r\n @b.c",
    "a\r@b.c",
    "a\n@b.c",
    "a@b.c\n",
    "a@b.c\r\n",
    "\r\na@b.c",
    "a@ ",
    "a@  ",
    " @b.c",
    "a\u00a0b@c.d",
    "a@b\u00a0c.d",
    "a\u3000b@c.d",
    # Буквальные адреса
    "a@[127.0.0.1]",
    "a@[127.0.0.256]",
    "a@[1.2.3]",
    "a@[1.2.3.]",
    "a@[1.2.3.4-]",
    "a@[.1.2.3.4]",
    "a@[IPv6:::1]",
    "a@[IPv6:2001:db8::1]",
    "a@[IPv6:2001:db8:1:2:3:4:5:6:7]",
    "a@[IPv6:1:2:3:4:5:6:1.2.3.4]",
    "a@[IPv6:::ffff:1.2.3.4]",
    "a@[IPv6:zz::1]",
    "a@[ipv6:::1]",
    "a@[IPv4:1.2.3.4]",
    "a@[]",
    "a@[",
    "a@]",
    "a@[1.2.3.4",
    "a@1.2.3.4]",
    "a@[[1.2.3.4]",
    "a@[1.2.[3.4]",
    "a@[1.2.3.4]]",
    "a@[1.2.3.4]x",
    "a@[1.2.3.4].c",
    "a@[1.2.3.4]@@@",
    "a@[1.2.3.4] ",
    "a@[1 .2.3.4]",
    "a@[1\t.2.3.4]",
    "a@[1\\.2.3.4]",
    "a@[1\x00.2.3.4]",
    "a@[1.2.3.4\r]",
    "a@[a b]",
    "a@[я]",
    "a@[😀]",
    "a@b[1.2.3.4]",
    "a@b.[1.2.3.4]",
    "a@(c)[1.2.3.4]",
    "[1.2.3.4]@b.c",
    "a@[1.2.3.4" + "5" * 300 + "]",
    "a@[" + "1" * 260 + "]",
    # IPv6 как слово в домене
    "a@IPv6",
    "a@ipv6",
    "a@b.IPv6",
    "a@IPv66.c",
    "a@\u212aIPv6.c",
    "a@IPv4.c",
    "IPv6@b.c",
    # Спецсимволы
    "a<b@c.d",
    "a>b@c.d",
    "a[b@c.d",
    "a]b@c.d",
    "a:b@c.d",
    "a::b@c.d",
    "a:::b@c.d",
    "a;b@c.d",
    "a,b@c.d",
    "a\\b@c.d",
    "a\\\\b@c.d",
    "a\\.b@c.d",
    "a\\ b@c.d",
    "a\\@c.d",
    "\\a@c.d",
    "a@b\\c.d",
    "a@b/c.d",
    "a@b<c.d",
    "a@b,c.d",
    "a@b:c.d",
    "a@b::c.d",
    "a@b;c.d",
    "a@b_c.d",
    "a@b+c.d",
    "a@b=c.d",
    "a@b!c.d",
    "a@b'c.d",
    'a@b"c.d',
    "a@b`c.d",
    "a@b~c.d",
    "a@b%c.d",
    "a@b#c.d",
    "a@b*c.d",
    "a@b&c.d",
    "a@b^c.d",
    "a@b$c.d",
    "a@b|c.d",
    "a@b{c}.d",
    "a@b?c.d",
    "a\x00b@c.d",
    "a@b\x00c.d",
    "\x00@b.c",
    "a\x01b@c.d",
    "a\x7fb@c.d",
    "a\x0bb@c.d",
    "a\x0cb@c.d",
    "a\x1bb@c.d",
    # Юникод
    "пользователь@пример.рф",
    "почта@savdex.uz",
    "user@пример.рф",
    "用户@例子.广告",
    "用户@例子.中国",
    "😀@b.c",
    "a@😀.c",
    "a😀@b.c",
    "a@b.😀",
    "a@b€.c",
    "€@b.c",
    "a©b@c.d",
    "a\u200db@c.d",
    "a@b\u200dc.d",
    "a\u200bb@c.d",
    "a\ufeffb@c.d",
    "a\u0301@b.c",
    "\u0301@b.c",
    "a@\u0301b.c",
    "a@b.\u0301c",
    "é@b.c",
    "a@é.c",
    "a@b.é",
    "a\u017fb@c.d",
    "\u017f@c.d",
    "a@\u017f.d",
    "a\u212a@c.d",
    "a@b\u212a.d",
    "straße@straße.de",
    "a@STRASSE.de",
    "a@ẞ.de",
    "a@ς.gr",
    "a@Ａ\uff22Ｃ.com",
    "a@b\u3002c",
    "a@b．c",
    "a@b｡c",
    "ǅ@ǅ.ǅ",
    "a@\U00010000.c",
    "a@\U0001f600",
    "a@\ue000.c",
    "a@\u0378.c",
    "a@\U000e0001.c",
    "a@b\U000e0100.c",
    "a@b\u00ad.c",
    "a@b\u2028c.d",
    "a@b\u0085c.d",
    "a@ⅷ.c",
    "a@①.c",
    "a@⑴.c",
    "a@\ufdfa.c",
    "a@" + "\ufdfa" * 14,
    "a@" + "\ufdfa" * 3 + ".c",
    "a@b.c" + "\ufdfa" * 14,
    "a@xn--я.c",
    "a@xn--80aswg" + "я" + ".c",
    "a@xn--ab-я.c",
    "a@я.xn--p1ai",
    "a@я.xn--",
    "a@я.xn--a-",
    "a@я.xn---",
    "a@я.xn--zz",
    "a@я.xn--A",
    "a@я.xn--ba-q6a",
    # Длины: локальная часть, метка, домен, весь адрес
    "a" * 64 + "@b.c",
    "a" * 65 + "@b.c",
    "a" * 250 + "@b.c",
    "a@" + "b" * 63,
    "a@" + "b" * 64,
    "a@" + "b" * 63 + ".c",
    "a@" + "b" * 64 + ".c",
    "a@c." + "b" * 62,
    "a@c." + "b" * 63,
    "a@c." + "b" * 62 + ".d",
    "a@c." + "b" * 63 + ".d",
    "a@" + ".".join(["b" * 63] * 4),
    "a@" + ".".join(["b" * 62] * 4),
    "a@" + ".".join(["b" * 50] * 5),
    "a@" + ".".join(["b" * 49] * 5),
    "a@" + "b." * 126 + "c",
    "a@" + "b." * 127 + "c",
    "a" * 64 + "@" + ".".join(["b" * 62] * 4),
    "a@" + "я" * 26,
    "a@" + "я" * 27,
    "a@" + "я" * 126,
    "a@" + "я" * 127,
    "a@" + "(" + "c" * 300 + ")b.c",
    "a@b(" + "c" * 300 + ").d",
    "(" + "c" * 300 + ")a@b.c",
    '"' + "a" * 300 + '"@b.c',
    "a@b.c" + " " * 300,
]

#: Части адреса для перебора «каждая с каждой»
ЛЕВЫЕ = [
    "a",
    "a.b",
    ".a",
    "a.",
    "a..b",
    '"a b"',
    '"a\\"b"',
    '"a',
    "(c)a",
    "a(c)",
    "a b",
    "a\\ b",
    "a\\b",
    "a\\\\",
    "я",
    "中",
    "a::b",
    "a:b",
    "a,b",
    "a_b+c",
    "IPv6",
    "a\t",
    " a",
    "a\r\n b",
    "\x00",
    "¡",
    "",
    "a@b",
    "a" * 64,
    "a" * 65,
]
ПРАВЫЕ = [
    "b",
    "b.c",
    "b.c.",
    ".b",
    "-b",
    "b-",
    "b-.c",
    "b.-c",
    "b..c",
    "b.1",
    "1.2.3.4",
    "[1.2.3.4]",
    "[IPv6:::1]",
    "[1.2.3.4",
    "(c)b.c",
    "b(c).d",
    "b(c)",
    "b c",
    " b",
    "b ",
    "b\t",
    "b\r\n c",
    "я.рф",
    "пример." + "я" * 20,
    "中.中",
    "b_c",
    "b:c",
    "b\\c",
    "",
    "@",
    "IPv6",
    "b" * 63,
    "b" * 64,
    "c." + "b" * 63,
    "xn--p1ai",
    "я" * 27,
    "ǅ",
    "ß" * 30,
    "straße.de",
]

АЗБУКА = [*'@."\\()[] \t-:,;<>ab1я中\r\n_+']


def _случайные() -> list[str]:
    случай = random.Random(20260928)
    строки = []

    for номер in range(3000):
        длина = случай.randint(1, 20)
        символы = [случай.choice(АЗБУКА) for _ in range(длина)]

        # У большинства ровно одна «@» посередине
        if номер % 3:
            символы = [c for c in символы if c != "@"] or ["a"]
            середина = len(символы) // 2
            символы.insert(середина, "@")

        строки.append("".join(символы))

    return строки


def _похожие() -> list[str]:
    """Случайные строки, похожие на адрес: больше букв, куски IDN и punycode."""
    случай = random.Random(28092026)
    обычные = [*"abcdefgh12.-яж中"]
    слева = [*'.._-+"( )\\', "xn--", "IPv6"]
    справа = [*"..-ßς( )[]:", "xn--", "\u0301", "\ufdfa", "\u3002", "\uff22", "\U0001f600"]
    строки = []

    def кусок(редкие: list[str], длина: int) -> str:
        return "".join(
            случай.choice(редкие if случай.random() < 0.1 else обычные) for _ in range(длина)
        )

    for _ in range(2000):
        левая = кусок(слева, случай.randint(1, 10))
        правая = кусок(справа, случай.randint(1, 40))
        строки.append(f"{левая}@{правая}")

    return строки


def _домены() -> list[str]:
    """Метки с не-ASCII около границы в 63 знака после punycode."""
    строки = []

    for буква in ["я", "中", "é", "ß", "ς", "a\u0301", "ǅ", "Я", "\ufdfa"]:
        for повтор in range(1, 64):
            метка = буква * повтор
            строки.append("a@" + метка)
            строки.append("a@b." + метка)
            строки.append("a@" + метка + ".c")
            строки.append("a@b" + "x" * (60 - повтор % 60) + метка)

    for длина in range(40, 66):
        строки.append("a@" + "b" * длина + "я")
        строки.append("a@c." + "b" * длина + "я")
        строки.append("a@xn--" + "b" * длина + "я")
        строки.append("a@c.xn--" + "b" * длина + "-я")

    return строки


def _точки() -> list[str]:
    """Каждый символ в двух местах: в локальной части и в домене."""
    строки = []

    for код in [*range(0x80, 0x3000), *range(0x3000, 0x30000, 7), *range(0xE0000, 0xE0200)]:
        if 0xD800 <= код <= 0xDFFF:
            continue
        c = chr(код)
        строки.append(f"a{c}b@x.uz")
        строки.append(f"a@x{c}y.uz")

    for код in range(0x80):
        c = chr(код)
        строки.append(f"a{c}b@x.uz")
        строки.append(f"a@x{c}y.uz")

    return строки


ВЕРНЫЕ = (
    "eNrtWkFrJEUUftPVM9PG3q2ZbBTF4E7iHuJBmGVgzaGxesMiUREiCh4NgqB4MC6KrpedLAH3ILgiiDeznvboHxBK"
    "RmSRwVbwIh4UFPRYWnoQCsuq6q6Z7umemWQ3iWPsl0x6ul+916++917Ve0WkkAR24IZ8uSXq7+JzbpN+JLfJuZvn"
    "twCgehqkJN/+9NuzL7194i1U/73+6Tb6CzK0+fV9q9fIrycWb9b1rZ8Z1j3/yo/hI9lhp/+onfwZ62EVq8MM+3v3"
    "4a3WZT0MD5T7+ZfSgmG3TN3RB5X8GEf/8YrlXdcZo2gyVSDcu023NCxvsGv+htM1O5PZ4fqX4DwQepcqVbTjXltc"
    "qGxeWZ5rwDvOh49D5SRcevXML94nTaex3UQefOBc3YRG837v6vyDa+tXNsD94sLcTqX6WkOZOPe9F0J3xQu7L57B"
    "CwvuqcrTLeiG3gVoOBuOqyyuuO5jdxijP3OWl6qw4LQbre6f0L0b7vSdRs1tvLC2vRhWr5+FJ7o1qEGrSaH7nfcQ"
    "uEvovd2LG++vN1qOt9F63QkdcL/R9p9dWWvBjdb1U7U3YR7B6ryCJvx4fnN1eaVZu2cH4NHK822v64Wf03uXNnbX"
    "YcuDr7ZXnqxcfGMCKc2T2Co5tqaIy5xEhrYO8u31nFunidcnR4WMKeprsg/rlAET4rJhkWSIvR4hYaY+2kgEnZSx"
    "xcSZBEa4mU0RP5r+vmgftgn7hYjUUwIiM8raTKiag6IAp0X3SD01ueQqcZZFxurCo3hFxE+zUx5ta7uTWZEilKO9"
    "g9Lrxc6QHaZe0esRoBBJ7UeJiRCEWj4PMFd32AfRAWagAyFkFFm+UPJRhDVsWh4pZEVKv+H3ehhErF8orJkgjOOA"
    "U0T0G5m+Q1QpYEa9nhnnibyBgHMMgcJF8YEaPIZ8YfkQaH6Qkbcxx2PgWCwjtDcIs5j5krSp7Cjd6hFTE8k6y2Iu"
    "B8kY8MQl/cRHHW0kHgxAWgrhWK4v0qGERD4yEbR17gSjyT417YaOB/9wM5xjSTjO3I9ySE5CjskBZMEcMyssZ5fS"
    "YYWKhyBIEpsm4QM2ekwkjvUv0TEE8UeHJYaJ+rOxmVlQUjsBpBa3GF2UeT9YoTjzMvHHRg0crnMDO/HAkPxmJUex"
    "QhoSlT4TEc6JaxixmICByAoRmIlIScex+d7v5/LWLsFc4cOML5D5PpgDpnapiJKcwQYLHBgQCjDXD9tUuc4XGDo8"
    "MuuSwO38rnOYZJfC4GC1jkZKjtg4xozQGOuDoflHYQUdREqRzwDPEEr7I6TXl9RSkdsXgSJIrctk5GcCscNPmtT8"
    "eWq3QcpqzIAAomjUh/8PsnldUkklZVqTzFqZVEm2eOipVonrwoEL01cma6JuXrDoRTzuF6MSxplyqRAzXL8cHOVW"
    "dEzbpiVGLNfjqm2dJ7tzsjFiPYqbrd7U1mm1PZKMCpJSgJveJW4TWPqgRSlByUYaAVUJgmJ+R/a5PgrqCGUR7/jm"
    "REAfPKh74qf2ae0qbRtVKUejuEzAoqOTisedCTb8SKlpYzttlZ5RvJMrfbrC577iAyXSt/t/XKUQZbU2kCBhzGep"
    "oo3F/ZkZx5nspCqDpBejeHohZQsJIQtLwoN3OdvrujZbJMaAV9Ltpr3JTd0ZC5U/lMsJgiS+qFxBx7oi3NcJvjk3"
    "LelAUjvXVR1O/HOO/jPYFK3Ekd9OTUjPRQw7UkxyRaWwv+oxLjyMwG2xV/zwAMiBfAZOSfe3ezAhh0dt0VQwmNWu"
    "vuBAFO+YR3FQgPYZ2yWVVFJJJR3/Q6FZtIofS6x7Zbj9Sz07m5WGnN4mZoP/GHzqroUfVD/XTMrRZ+Lrc9V/ACoV"
    "+uI="
)
ВЕРНЫЕ_СТРОГО = (
    "eNrtWM2KHDcQrmntjjumsWbNBgwJZAg+OIdAm7740KB2SMBHJyTnLCbk7FuOGee05JRH8DlPIejrQF98TyAvoKCr"
    "QKmSWjPq6Z7ZGby7mWy67J3+kaq69NWPqvTTOytgAfMHEGjB6Fc+f42/p5+AtU/f/fX3y88gfQT34DRbsAUcQBP2"
    "J8zpppLwDJ5cwMdwnsMDuE/SJp1pbxeT1zDrsg98dDEwbaRbpApNmbAKjXY6QbOcnE8ukiQBuIS0gkkCT/PHkOYA"
    "swUZ+AQu5zCbzVJIUnjxC/InX6bINiMTph8Bypmn9INud/Jw8nDuPzJLKmR19MJfnifJnN7QhB9gkcD9jKTD4y/e"
    "IP/8DEjqFIclwG/p53CCqiy+qc6qGSTwcv4dVKij95snOCuFt5Op+9gj9+5TmOeQnpHWMJ28wokpLKoP5hU+X6DX"
    "vUE9Xv24g1DGruEpijmMfbqB+8V1fn3aM+tV7NPdXvG7p18vicLLe1KBMuZnSySs7VxvkbjCP9THMihIr52TtbKg"
    "hKbbZmi8ufp7zQG6mXAjTPRWgOnMCjoLaV1+LnnMuifVuLj2anl3SGyVxTfxakQWD0cWzUnvdlViCOVmf1Dq2hvD"
    "Fgo/UdcC47qxZEfLhTFChnFdco1PPANTgHLQgTG2acK4Qf6m4QQb8TNE1kTy3XhdczBevkGslRFK81JLJuiLip4Y"
    "5hWSLzweWrf8DgKtOZSIC46DdHisx00Yh5LGyw5/8DntgVOex5A1hAqYZVbk0hYoG18pXEjXWAFzuwrGUrcmWbY2"
    "KkhJvprAiItxz7c0sSsx0/dMBjnFTrmSv2/YrQ0P2c1GuOZWaN553hwRPQ67JQZYAHPLqrg9Xordig1PYdAGtmzd"
    "B4L3OE/cal9BPgT+j9ySw075Xd/sJJRoJ4AouXl0Wef7EJh85HX8T20quM5zKz35SpGIhpT2mkvSptyJcI+dYORm"
    "BwamyyTgKDwl9mN3v1z24jakYI34KGcL5u5Xa+AypIqmjRnusOClA2EAc3qZSzRdZjgUunF5yfC8v+vcJIVUWF6v"
    "1E1P6ZHaNnAktEX7cq3+bWghV54yZDPgR4TSYcQov0SporcvgmQQ5WWx8W8HqZsPmmj9OtptGGrNFQhgkm3a8P9B"
    "Ia5HGmmkTmvSyZVtlRSKhxpbJU2Fgzaur2xzIjUv3NSN9v1iM8J4VCY15ojrl+ujXkbnMnctMVO9Hhe3dd3uzu3G"
    "yGmWdlu9q61jsbVoZ5VtKaBd7+LbBBUftKAQ1m6kDUgMEObHC7vUdBRUGNRIF5k7EaCDB3wWWbRPk6lIN4khJxtf"
    "JnBTUFBp35lwN96gmJyHZWN4Nn4nR3lU4esMx0EKm4X931cpArUmBQUzTn0VFW3K92dunla2iCqDtheT/OpCKhQS"
    "xg6WhNdvcrVvXjsuMlvAG+l9w97FJnXGBuNHaruDUfgLxgq70xXhQSf47tx0pGsJ7V5XdTP+rzX7z2AzlImbLI8W"
    "RGsx646Ui15RacJ/fM0HDyN4bvbFj6+AXPF34LTysN1DGbs+amuuBEMF6XjDSzO8Y97GQQE70LdHGmmkkUa6+4dC"
    "x6iVvpNY16O7/Us9uzqWhly+J2ZVEPT1h+d/YD931paj3/rr919N/wFf3qjz"
)
НЕНАЗНАЧЕННЫЕ = (
    "eNrtWM9r1EAU/vIDUyTY7PYSpbAREVrwEDwtIiYn8WYv3iPevNjjgtLMobQePIgHr93+B8W/ICxSehRPxYuhCnoM"
    "Pa2YZnwzSbpJqK1bWrvofmEyeTNvZt588+bN7ALnCm12AdDHbqZQYor8tPMMnFIv5ic29YvcrhamvFYagdF7C0Mx"
    "THpsd1ZwCVDvmMFa+NAl7VZPyG9u9bYPNj0w3vJpdmrb9N9n3EWqtKR+2wy2O0Kfz3UHi9+6uNsdrHAPNKKjUj1M"
    "Z7Cx6yJELltC3nDxg0sZongW1B4tMI0Y/MCe9+HhCy/Y6FFKOGFxBliiGfUjmEKuURgr5ZdDz7BW36Tt85hLNGCD"
    "PC8FVlagwnUsyB81iqJz8LG48p3RGEQq44IeOPvV+UZkSVq3R+gD0g9yFaHPkCC5IsXC3xLZqlsouUUuJhzIPsWs"
    "GOc1fuNDnQqS2eLDwHzNAhu8bsnpkXNM70dyzrk30eNawI2aPQ5MYaG0NOOjd93ks18wQZXwRvzzcCsB6U+QKLW9"
    "GGbSl1mB5kIX/lYJr8kxnAr1fDXJIp1hiilQCWWE+SKoGQs+2vDpaPFVzN9X9bGceJJR3iYuhORn10XgL68krOT9"
    "LZwOIh9xZ0hXhDUHeN0RwZkxJfGk7uq9mAKBH67GJF++yYxrlvOJK4lhW7vy1LGS0FkeLutw2SZ0FXYUOr7yLqX+"
    "EnzlvGO9wEdlf13GAAoqL1lmfFdsaLForblIQtzuy67WKRkzTdt5KO8RMR8L3uFZWevrjKBUwt6kwhut/hIsPVCr"
    "lRqjemWPaxew1ZtY4ZONTu46xpgL7sHZOw9riMVM+J9LO4VpZM4T2FxY96o8jy00z377KPtS4QeUQieTBcvs6BHn"
    "xAlu+I0dMPSEurZzNd+YNH5brG/2uP+zuj9GCLCjPHDT3C2jIH4qyDw4xm2nmOK/QnJ2NwT971ltTgR3p4ymxujn"
    "+O+VDhp/XjTrT7LsF3DnAyA="
)


ДЛИННЫЕ = [
    # Локальная часть больше 64 байт, весь адрес больше 254
    "a" * 64 + "@savdex.uz",
    "a" * 65 + "@savdex.uz",
    "я" * 33 + "@savdex.uz",
    "a" * 60 + "@" + ".".join(["b" * 60] * 3) + ".uz",
    "a" * 64 + "@" + ".".join(["b" * 60] * 3) + ".uzb",
    "user@localhost",
    "user@[127.0.0.1]",
    '"quoted"@savdex.uz',
    "user(comment)@savdex.uz",
    "user @savdex.uz",
]


def _биты(packed: str, count: int) -> list[bool]:
    data = zlib.decompress(base64.b64decode(packed))
    assert len(data) == (count + 7) // 8

    return [bool(data[i // 8] >> (i % 8) & 1) for i in range(count)]


def _набор() -> list[str]:
    return [
        *АДРЕСА,
        *(f"{левая}@{правая}" for левая in ЛЕВЫЕ for правая in ПРАВЫЕ),
        *_случайные(),
        *_похожие(),
        *_домены(),
        *_точки(),
    ]


def _та_же_версия_unicode(строки: list[str]) -> set[str]:
    """
    Знаки, которые при записи ответа были неназначенными (Cn), а в этом
    Python назначены, — или наоборот. Ответ записан при Unicode 14
    (у unicodedata и PCRE2 тогда совпадали все категории); в новом Python
    знак новой версии для правила уже буква, и такие строки не сверяются:
    это разница окружения, а не правила.
    """
    знаки = sorted({ch for s in строки for ch in s if ord(ch) > 127})
    были = _биты(НЕНАЗНАЧЕННЫЕ, len(знаки))

    return {
        ch for ch, cn in zip(знаки, были, strict=True) if (unicodedata.category(ch) == "Cn") != cn
    }


def _не_совпали(строки: list[str], ответ: list[bool], strict: bool) -> list[tuple[str, bool]]:
    чужие = _та_же_версия_unicode([*_набор(), *ДЛИННЫЕ])

    return [
        (s, e)
        for s, e in zip(строки, ответ, strict=True)
        if not чужие.intersection(s) and is_valid(s, strict=strict) is not e
    ]


def test_как_у_egulias():
    строки = _набор()
    ответ = _биты(ВЕРНЫЕ, len(строки))
    расхождения = _не_совпали(строки, ответ, strict=False)

    assert not расхождения, расхождения[:20]
    assert sum(ответ) > 1000
    assert len(строки) - sum(ответ) > 1000


def test_строго_как_у_egulias():
    """email:rfc,strict: верен и без предупреждений разбора."""
    строки = [*_набор(), *ДЛИННЫЕ]
    ответ = _биты(ВЕРНЫЕ_СТРОГО, len(строки))
    расхождения = _не_совпали(строки, ответ, strict=True)

    assert not расхождения, расхождения[:20]
    assert sum(ответ) > 500


#: Адрес → верен ли (без strict, со strict) — по смыслу RFC 5321/5322
ПОНЯТНЫЕ = {
    "user@savdex.uz": (True, True),
    "user.name+tag@savdex.uz": (True, True),
    "пользователь@пример.рф": (True, True),
    # Домен без точки и адрес в скобках RFC допускает, но со strict это
    # предупреждения
    "user@localhost": (True, False),
    "user@[127.0.0.1]": (True, False),
    # Кавычки и комментарии — верно, но со strict это предупреждения
    '"a b"@savdex.uz': (True, False),
    "user(comment)@savdex.uz": (True, False),
    # Локальная часть длиннее 64 байт — только предупреждение
    "a" * 64 + "@savdex.uz": (True, True),
    "a" * 65 + "@savdex.uz": (True, False),
    # Метка домена — не длиннее 63 знаков
    "a@" + "b" * 63 + ".uz": (True, True),
    "a@" + "b" * 64 + ".uz": (False, False),
    "": (False, False),
    "user": (False, False),
    "user@": (False, False),
    "@savdex.uz": (False, False),
    "a@@b": (False, False),
    ".a@b.c": (False, False),
    "a.@b.c": (False, False),
    "a..b@c.d": (False, False),
    "a@b..c": (False, False),
    "a@-b.c": (False, False),
    "a b@c.d": (False, False),
    "a<b@c.d": (False, False),
    "a@b_c.d": (False, False),
    "😀@b.c": (False, False),
}


def test_понятные_случаи():
    for адрес, (верен, строго) in ПОНЯТНЫЕ.items():
        assert is_valid(адрес) is верен, адрес
        assert is_valid(адрес, strict=True) is строго, адрес


def test_не_строка():
    assert not is_valid(None)
    assert not is_valid(5)
    assert not is_valid(["a@b.c"])
    assert not is_valid(b"a@b.c")


def test_перевод_строки():
    assert not is_valid("a@b.c\n")
    assert not is_valid("a\r@b.c")
    assert is_valid("a@b.c")
