"""
Правило email на Python совпадает с validateEmail у Laravel (RFCValidation
из egulias/email-validator): те же строки прогоняются через PHP (один
процесс) и через savdex.web.email_rfc.

Обработчик ошибок в PHP — как у Laravel (HandleExceptions): предупреждение
становится ErrorException, устаревания молчат. Без него иначе вёл бы себя
idn_to_ascii с переполненным ответом.
"""

from __future__ import annotations

import json
import random
import shutil
import subprocess
import unicodedata

import pytest

from savdex.web.email_rfc import is_valid

from .pg_admin import КОРЕНЬ

PHP = r"""
require 'vendor/autoload.php';

use Egulias\EmailValidator\EmailValidator;
use Egulias\EmailValidator\Validation\MultipleValidationWithAnd;
use Egulias\EmailValidator\Validation\RFCValidation;

error_reporting(-1);
set_error_handler(function ($level, $message, $file = '', $line = 0) {
    if (in_array($level, [E_DEPRECATED, E_USER_DEPRECATED], true)) {
        return true;
    }
    if (error_reporting() & $level) {
        throw new ErrorException($message, 0, $level, $file, $line);
    }
    return true;
});

$in = json_decode(stream_get_contents(STDIN), true);

echo json_encode(array_map(function ($s) {
    if (preg_match('/[\r\n]/', $s) > 0) {
        return false;
    }

    return (new EmailValidator)->isValid($s, new MultipleValidationWithAnd([new RFCValidation]));
}, $in));
"""

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


def _php(values: list[str], strict: bool = False) -> list[bool]:
    код = PHP

    if strict:
        # email:rfc,strict у Laravel — RFCValidation и NoRFCWarningsValidation
        код = PHP.replace(
            "new MultipleValidationWithAnd([new RFCValidation])",
            "new MultipleValidationWithAnd([new RFCValidation,"
            " new \\Egulias\\EmailValidator\\Validation\\NoRFCWarningsValidation])",
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


#: Общие категории Unicode — PHP сообщает свою для каждого знака
КАТЕГОРИИ = (
    "Lu",
    "Ll",
    "Lt",
    "Lm",
    "Lo",
    "Mn",
    "Mc",
    "Me",
    "Nd",
    "Nl",
    "No",
    "Pc",
    "Pd",
    "Ps",
    "Pe",
    "Pi",
    "Pf",
    "Po",
    "Sm",
    "Sc",
    "Sk",
    "So",
    "Zs",
    "Zl",
    "Zp",
    "Cc",
    "Cf",
    "Cs",
    "Co",
    "Cn",
)


def _категории_php(знаки: list[str]) -> list[str]:
    """Категория каждого знака по таблицам PCRE2, с которыми собран PHP."""
    код = (
        "$in = json_decode(stream_get_contents(STDIN), true);"
        "$cats = " + json.dumps(list(КАТЕГОРИИ)) + ";"
        "echo json_encode(array_map(function ($ch) use ($cats) {"
        " foreach ($cats as $c) { if (preg_match('/^\\p{' . $c . '}$/u', $ch)) return $c; }"
        " return '?'; }, $in));"
    )
    вывод = subprocess.run(
        ["php", "-r", код],
        input=json.dumps(знаки),
        capture_output=True,
        text=True,
        check=True,
    )

    return json.loads(вывод.stdout)


def _та_же_версия_unicode(строки: list[str]) -> list[str]:
    """
    Только строки из знаков, которые Python и PHP относят к одной
    категории. Версии Unicode у unicodedata и у PCRE2 бывают разные
    (в CI Python новее): знак, назначенный в новой версии, для одной
    стороны буква, для другой — неназначенный. Это разница окружения, а
    не переноса, и такие строки не сверяются.
    """
    знаки = sorted({ch for s in строки for ch in s if ord(ch) > 127})
    чужие = {
        ch
        for ch, php in zip(знаки, _категории_php(знаки), strict=True)
        if unicodedata.category(ch) != php
    }

    return [s for s in строки if not чужие.intersection(s)]


@pytest.mark.skipif(shutil.which("php") is None, reason="нужен PHP")
def test_как_у_laravel():
    строки = [
        *АДРЕСА,
        *(f"{левая}@{правая}" for левая in ЛЕВЫЕ for правая in ПРАВЫЕ),
        *_случайные(),
        *_похожие(),
        *_домены(),
        *_точки(),
    ]
    строки = _та_же_версия_unicode(строки)
    ожидание = _php(строки)
    расхождения = [(s, e) for s, e in zip(строки, ожидание, strict=True) if is_valid(s) is not e]

    assert not расхождения, расхождения[:20]
    assert sum(ожидание) > 1000
    assert len(строки) - sum(ожидание) > 1000


@pytest.mark.skipif(shutil.which("php") is None, reason="нужен PHP")
def test_строго_как_у_laravel():
    """email:rfc,strict: верен и без предупреждений разбора."""
    строки = [
        *АДРЕСА,
        *(f"{левая}@{правая}" for левая in ЛЕВЫЕ for правая in ПРАВЫЕ),
        *_случайные(),
        *_похожие(),
        *_домены(),
        *_точки(),
        # Длинные: локальная часть больше 64 байт, весь адрес больше 254
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
    строки = _та_же_версия_unicode(строки)
    ожидание = _php(строки, strict=True)
    расхождения = [
        (s, e) for s, e in zip(строки, ожидание, strict=True) if is_valid(s, strict=True) is not e
    ]

    assert not расхождения, расхождения[:20]
    assert sum(ожидание) > 500


def test_не_строка():
    assert not is_valid(None)
    assert not is_valid(5)
    assert not is_valid(["a@b.c"])
    assert not is_valid(b"a@b.c")


def test_перевод_строки():
    assert not is_valid("a@b.c\n")
    assert not is_valid("a\r@b.c")
    assert is_valid("a@b.c")
