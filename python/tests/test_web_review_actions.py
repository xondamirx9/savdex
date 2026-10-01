"""
Отзывы о своей компании на Django: ответ на
отзыв (10–2000 знаков, повторный заменяет прежний, свои тексты ошибок)
и спор (один, причина 20–1000 знаков). Отзыв о чужой компании или
неопубликованный — 404. У администратора — строка журнала.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from .factories import компания, отзыв
from .pg_admin import sql, нужна_база, свежая_база
from .test_web_forms import inertia, отправить, учётка
from .web_site import адрес

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    c = компания(slug="seller")
    o = компания(slug="other")

    for to, status in ((c, "published"), (c, "moderation"), (o, "published")):
        отзыв(company_id=to, status=status, body="Хороший поставщик")

    with адрес() as root:
        yield root


def продавец(admin: bool = False) -> int:
    cid = int(sql("select id from companies where slug = 'seller'")[0][0])

    return учётка("seller@savdex.uz", company_id=cid, is_admin=admin)


def отзывы(slug: str = "seller") -> list[int]:
    return [
        int(r[0])
        for r in sql(
            "select r.id from reviews r join companies c on c.id = r.company_id "
            "where c.slug = %s order by r.id",
            [slug],
        )
    ]


def сброс(ответ: str | None = None, спор: bool = False) -> Callable[[], None]:
    def run() -> None:
        sql("delete from admin_actions where section = 'reviews'")
        sql(
            "update reviews set reply = %s, replied_at = %s, dispute_status = %s, "
            "dispute_reason = null, updated_at = now() - interval '1 day'",
            [
                ответ,
                "2026-09-01 10:00:00" if ответ else None,
                "pending" if спор else None,
            ],
        )

    return run


def снимок() -> Any:
    журнал = [
        (u, a, s, sid, label, re.sub(r"\d{4}-\d\d-\d\d \d\d:\d\d:\d\d", "T", ch or ""))
        for u, a, s, sid, label, ch in sql(
            "select user_id, action, section, subject_id, subject_label, changes::text "
            "from admin_actions where section = 'reviews' order by id"
        )
    ]

    return {
        "reviews": sql(
            "select reply, replied_at is not null, replied_at > now() - interval '1 hour', "
            "dispute_status, dispute_reason, updated_at > now() - interval '1 hour', "
            "rating from reviews order by id"
        ),
        "journal": журнал,
    }


ОТВЕТ = "Спасибо за отзыв, будем рады новым заказам!"
ПРИЧИНА = "Покупатель ничего у нас не заказывал, сделки не было"


def сессия(итог: dict[str, Any]) -> dict[str, Any]:
    """Сессия после ответа: сообщение (success/error) и ошибки проверки по полям."""
    payload = json.loads(итог["сессия"]["payload"])
    ошибки = payload.get("errors", {}).get("default", {}).get("messages", {})

    return {"success": payload.get("success"), "error": payload.get("error"), "errors": ошибки}


@pytest.mark.parametrize("admin", [False, True])
@pytest.mark.parametrize(
    ("body", "прежний", "ошибка"),
    [
        ({"reply": ОТВЕТ}, None, None),
        ({"reply": ОТВЕТ}, ОТВЕТ, None),
        ({"reply": "Другой ответ, подробнее"}, ОТВЕТ, None),
        ({"reply": "коротко"}, None, "Ответ слишком короткий"),
        ({}, None, "Напишите ответ"),
        ({"reply": "x" * 2001}, None, ""),
        ({"reply": ["массив"]}, None, ""),
    ],
)
def test_ответ(сайт, body, прежний, ошибка, admin):
    итог = отправить(
        сайт,
        f"/cabinet/reviews/{отзывы()[0]}/reply",
        сброс(прежний),
        снимок,
        uid=продавец(admin),
        body=body,
        headers=inertia(),
    )
    ответ, итог_сессии = итог["ответ"], сессия(итог)
    reply, есть, свежий = итог["база"]["reviews"][0][:3]
    записан = admin and body.get("reply") in (ОТВЕТ, "Другой ответ, подробнее")

    # Назад, откуда пришла форма
    assert ответ["status"] == 302
    assert ответ["headers"]["location"] == сайт + "/cabinet/settings"

    if ошибка is None:
        # Ответ (и повторный — заменяет прежний) с новой отметкой времени
        assert итог_сессии["success"] == "Ответ опубликован" and not итог_сессии["errors"]
        assert (reply, есть, свежий) == (body["reply"], True, True)
    else:
        assert list(итог_сессии["errors"]) == ["reply"]
        assert ошибка in итог_сессии["errors"]["reply"][-1]
        assert reply == прежний and итог_сессии["success"] is None

    assert bool(итог["база"]["journal"]) is записан, итог["база"]["journal"]


@pytest.mark.parametrize(
    ("prefix", "сообщения"),
    [
        ("", ("Отзыв отправлен на проверку модератору", "Отзыв уже на рассмотрении")),
        ("/en", None),
        ("/uz", None),
    ],
)
@pytest.mark.parametrize(
    ("body", "спор", "принят"),
    [
        ({"reason": ПРИЧИНА}, False, True),
        ({"reason": ПРИЧИНА}, True, False),
        ({"reason": "мало"}, False, False),
        ({"reason": ""}, False, False),
        ({"reason": "x" * 1001}, False, False),
    ],
)
def test_спор(сайт, body, спор, принят, prefix, сообщения):
    итог = отправить(
        сайт,
        f"{prefix}/cabinet/reviews/{отзывы()[0]}/dispute",
        сброс(спор=спор),
        снимок,
        uid=продавец(True),
        body=body,
        headers=inertia(),
    )
    ответ, итог_сессии = итог["ответ"], сессия(итог)
    _, _, _, статус, причина, изменён, _ = итог["база"]["reviews"][0]

    assert ответ["status"] == 302
    assert ответ["headers"]["location"] == f"{сайт}{prefix}/cabinet/settings"

    if принят:
        # Спор открыт с причиной, в журнале администратора — строка
        assert (статус, причина, изменён) == ("pending", ПРИЧИНА, True)
        assert итог_сессии["success"] and not итог_сессии["errors"]
        assert len(итог["база"]["journal"]) == 1
    elif спор:
        # Второй спор не открывается: прежний на месте
        assert (статус, причина, изменён) == ("pending", None, False)
        assert итог_сессии["error"] and итог_сессии["success"] is None
        assert итог["база"]["journal"] == []
    else:
        assert list(итог_сессии["errors"]) == ["reason"]
        assert (статус, причина, изменён) == (None, None, False)
        assert итог["база"]["journal"] == []

    if сообщения is not None:
        if принят:
            assert итог_сессии["success"] == сообщения[0]
        elif спор:
            assert итог_сессии["error"] == сообщения[1]


@pytest.mark.parametrize("which", ["moderation", "other"])
def test_не_свой_отзыв_404(сайт, which):
    номер = отзывы()[1] if which == "moderation" else отзывы("other")[0]
    итог = отправить(
        сайт,
        f"/cabinet/reviews/{номер}/reply",
        сброс(),
        снимок,
        uid=продавец(),
        body={"reply": ОТВЕТ},
    )

    assert итог["ответ"]["status"] == 404
    assert all(r[0] is None for r in итог["база"]["reviews"])
