"""
Данные страницы в <script type="application/json"> (savdex/web/inertia.page_json):
«<!--<script>» в отзыве или названии компании не должно ломать разбор HTML.
Браузер, встретив внутри <script> «<!--<script», перестаёт считать
следующий </script> закрывающим — и остаток страницы съедается. Поэтому
в данных страницы нет ни одного «<».
"""

from __future__ import annotations

import json

from savdex.web.inertia import page_json

ОПАСНОЕ = "Отличный поставщик <!--<script> и </script> <b>жирно</b>"


def test_нет_знака_меньше():
    text = page_json({"props": {"review": ОПАСНОЕ, "list": [ОПАСНОЕ]}})

    assert "<" not in text
    assert json.loads(text) == {"props": {"review": ОПАСНОЕ, "list": [ОПАСНОЕ]}}
