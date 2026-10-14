"""
Значок сайта (<link rel="icon">): знак из коробки — с полями, свой — как есть.

Google и соцсети обрезают значок кругом. Знак logo-mark.svg занимает
квадрат до краёв, и в выдаче у него срезались самолёт и росчерк, поэтому
значком служит вариант с полями — favicon.svg. Логотип, загруженный
в «Оформлении», остаётся значком вкладки, как обещает подсказка.
"""

from __future__ import annotations

import math
import re
from pathlib import Path

from savdex.web.shared import DEFAULT_ICON, DEFAULT_LOGO, appearance_icon, appearance_logo

PUBLIC = Path(__file__).resolve().parents[2] / "public"


def test_знак_из_коробки_значком_с_полями():
    assert appearance_logo({}) == DEFAULT_LOGO
    assert appearance_icon(DEFAULT_LOGO) == DEFAULT_ICON


def test_свой_логотип_значком_как_есть():
    свой = "/storage/appearance/znak.svg"

    assert appearance_icon(свой) == свой


def test_значок_с_полями_тот_же_знак():
    знак = (PUBLIC / "images/logo-mark.svg").read_text(encoding="utf-8")
    значок = (PUBLIC / "images/favicon.svg").read_text(encoding="utf-8")

    def рисунок(svg: str) -> str:
        без_комментариев = re.sub(r"<!--.*?-->", "", svg, flags=re.S)
        return re.sub(r'viewBox="[^"]*"|\s+', "", без_комментариев)

    # Отличается только рамка: сам знак — тот же
    assert рисунок(значок) == рисунок(знак)


def test_поля_вмещают_круг():
    """
    Знак целиком внутри круга, вписанного в рамку: охватывающий круг знака
    (центр 260, 220, радиус около 265 в единицах рисунка, замерен по
    отрисовке) меньше вписанного круга рамки.
    """
    значок = (PUBLIC / "images/favicon.svg").read_text(encoding="utf-8")
    x, y, w, h = (float(v) for v in re.search(r'viewBox="([^"]+)"', значок)[1].split())

    assert w == h
    centre = (x + w / 2, y + h / 2)
    assert math.hypot(centre[0] - 260, centre[1] - 220) + 265 < w / 2
