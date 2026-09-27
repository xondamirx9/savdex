"""
Постраничный вывод — копия LengthAwarePaginator: сверка с настоящим
Laravel на сотне сочетаний «всего, на странице, текущая, запрос».

Окно номеров с «...» (UrlWindow) появляется только от 14 страниц —
в тестах страниц сайта столько данных нет, поэтому окно сверяется
здесь, на самом классе Laravel. Нужен PHP.
"""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest

from savdex.web import paginator

from .pg_admin import КОРЕНЬ

pytestmark = pytest.mark.skipif(shutil.which("php") is None, reason="нужен PHP")

СЛУЧАИ = [
    (total, per_page, current, query)
    for total in (0, 1, 19, 20, 21, 95, 260, 281, 300, 1000)
    for per_page in (20,)
    for current in (1, 2, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 50)
    for query in ("", "page=3&q=%D1%86%D0%B5%D0%BC%D0%B5%D0%BD%D1%82&a%5B%5D=1&a%5B%5D=2&b=~")
]

#: Отдельным скриптом, а не через tinker: тот портит строку «...»
PHP = r"""<?php
require 'vendor/autoload.php';
$app = require 'bootstrap/app.php';
$app->make(Illuminate\Contracts\Console\Kernel::class)->bootstrap();
$cases = json_decode(stream_get_contents(STDIN), true);
$out = [];
foreach ($cases as [$total, $perPage, $current, $query, $locale]) {
    app()->setLocale($locale);
    parse_str($query, $params);
    $items = array_slice(range(1, max($total, 1)), ($current - 1) * $perPage, $perPage);
    $items = $total === 0 ? [] : $items;
    $p = new Illuminate\Pagination\LengthAwarePaginator($items, $total, $perPage, $current,
        ['path' => 'http://savdex.test/uz/resumes', 'pageName' => 'page']);
    $out[] = $p->appends($params)->toArray();
}
echo json_encode($out);
"""


def test_как_у_laravel(tmp_path):
    cases = [[*case, locale] for case in СЛУЧАИ for locale in ("ru", "en")]
    script = tmp_path / "paginator.php"
    script.write_text(PHP)
    result = subprocess.run(
        ["php", str(script)],
        cwd=КОРЕНЬ,
        input=json.dumps(cases),
        capture_output=True,
        text=True,
        check=True,
    )
    expected = json.loads(result.stdout.strip().splitlines()[-1])

    for case, want in zip(cases, expected, strict=True):
        total, per_page, current, query, locale = case
        items = list(range(1, max(total, 1) + 1))[(current - 1) * per_page : current * per_page]
        page = paginator.Page(items if total else [], total, per_page, current)
        got = paginator.build("http://savdex.test/uz/resumes", query, locale, page)

        assert got == want, case
