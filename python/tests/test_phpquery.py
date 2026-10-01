"""
Строка запроса, как у Laravel: нормализация (Request::normalizeQueryString
у Symfony) и ввод после TrimStrings/ConvertEmptyStringsToNull.

Ожидаемые значения — литералы: так эти же строки разбирали Symfony
и Laravel (parse_str, ksort, http_build_query с RFC 3986), и Python
обязан дать ровно тот же результат — от него зависят адреса страниц
(full_url) и то, что видят формы.
"""

from __future__ import annotations

from savdex.web.phpquery import build_query, full_path, laravel_input, normalize

#: Строка запроса → нормализованная: ключи по ksort (числа и строки
#: вперемешку, как у PHP), повторы — последний, пробел — %20,
#: «[]» — индексы, незакрытая «[» остаётся в имени
СЛУЧАИ = {
    "type=platform&page=2": "page=2&type=platform",
    "b=1&a=2&a=3": "a=3&b=1",
    "a=%20x&a=y+z": "a=y%20z",
    "q=цемент+м400&page=1": "page=1&q=%D1%86%D0%B5%D0%BC%D0%B5%D0%BD%D1%82%20%D0%BC400",
    "a[]=1&a[]=2&b[x]=3&b[y][]=4": "a%5B0%5D=1&a%5B1%5D=2&b%5Bx%5D=3&b%5By%5D%5B0%5D=4",
    "a[b=1": "a%5Bb=1",
    "a[b]c=1&a[d]=2": "a%5Bb%5D=1&a%5Bd%5D=2",
    "a=1&a[]=2": "a%5B0%5D=2",
    "a[]=2&a=1": "a=1",
    "=1&&x=&y": "x=&y=",
    "10=a&9=b&x=c&01=d&-1=e": "-1=e&01=d&9=b&10=a&x=c",
    "%E2%80%A6=1&%FF=2": "%E2%80%A6=1&%FF=2",
    "a%5Bb%5D=1": "a%5Bb%5D=1",
    "  lead=1&a.b=2&c d=3": "a.b=2&c%20d=3&lead=1",
    "a[0]=x&a[5]=y&a[]=z": "a%5B0%5D=x&a%5B5%5D=y&a%5B6%5D=z",
    "k=~tilde_-.": "k=~tilde_-.",
    "u=%C3%A9%2F%3F%26": "u=%C3%A9%2F%3F%26",
}


def test_как_у_symfony():
    assert {q: normalize(q) for q in СЛУЧАИ} == СЛУЧАИ


def test_путь_как_в_full_url():
    assert full_path("/", "") == ""
    assert full_path("/", "b=1&a=2") == "/?a=2&b=1"
    assert full_path("/reviews/", "type=platform&page=2") == "/reviews?page=2&type=platform"


#: Для laravel_input: строка → (ввод в виде http_build_query, ключи со
#: значением null). Ввод — без ksort, в порядке строки; пробелы Юникода
#: и невидимые знаки обрезаются, пустое — null, пароли не трогаются;
#: «.» и пробел в имени — «_», как у parse_str
ВВОД = {
    "type=platform&page=2": ("type=platform&page=2", []),
    "b=1&a=2&a=3": ("b=1&a=3", []),
    "a=%20x&a=y+z": ("a=y%20z", []),
    "q=цемент+м400&page=1": ("q=%D1%86%D0%B5%D0%BC%D0%B5%D0%BD%D1%82%20%D0%BC400&page=1", []),
    "a[]=1&a[]=2&b[x]=3&b[y][]=4": ("a%5B0%5D=1&a%5B1%5D=2&b%5Bx%5D=3&b%5By%5D%5B0%5D=4", []),
    "a[b=1": ("a_b=1", []),
    "a[b]c=1&a[d]=2": ("a%5Bb%5D=1&a%5Bd%5D=2", []),
    "a=1&a[]=2": ("a%5B0%5D=2", []),
    "a[]=2&a=1": ("a=1", []),
    "=1&&x=&y": ("", ["x", "y"]),
    "10=a&9=b&x=c&01=d&-1=e": ("10=a&9=b&x=c&01=d&-1=e", []),
    "%E2%80%A6=1&%FF=2": ("%E2%80%A6=1&%FF=2", []),
    "a%5Bb%5D=1": ("a%5Bb%5D=1", []),
    "  lead=1&a.b=2&c d=3": ("lead=1&a_b=2&c_d=3", []),
    "a[0]=x&a[5]=y&a[]=z": ("a%5B0%5D=x&a%5B5%5D=y&a%5B6%5D=z", []),
    "k=~tilde_-.": ("k=~tilde_-.", []),
    "u=%C3%A9%2F%3F%26": ("u=%C3%A9%2F%3F%26", []),
    "q=%20%20Excel%C2%A0&e=&page=%202%20": ("q=Excel&page=2", ["e"]),
    "q=%E2%80%8B%D1%86%D0%B5%D0%BC%D0%B5%D0%BD%D1%82%E3%80%80": (
        "q=%D1%86%D0%B5%D0%BC%D0%B5%D0%BD%D1%82",
        [],
    ),
    # null внутри массива не попадает в http_build_query
    "a[]=%20x&a[]=&b[c]=%09y%0A": ("a%5B0%5D=x&b%5Bc%5D=y", []),
    "password=%20p%20&current_password=%20&name=%20": (
        "password=%20p%20&current_password=%20",
        ["name"],
    ),
    "bad=%FF%20&ok=%20%20": ("bad=%FF", ["ok"]),
    # имена, которые parse_str самого PHP портит, а Symfony — нет
    "a[b.c d=1&x[=2&a.b[c.d]=3&[z]=4&a]b=5&a.b[=6": (
        "a_b_c_d=1&x_=2&a_b%5Bc.d%5D=3&a%5Db=5&a_b_=6",
        [],
    ),
}


def test_ввод_после_trim_strings():
    got = {}

    for q in ВВОД:
        data = laravel_input(q)
        got[q] = (build_query(data), [str(k) for k, v in data.items() if v is None])

    assert got == ВВОД
