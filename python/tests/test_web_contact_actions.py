"""
«Мои контакты» на Django: статус и заметка
(PATCH, проверка ввода), жалоба на нерабочий контакт (одна, причина
10–500 знаков, свои тексты ошибок), выгрузка в CSV (BOM, «;», кавычки
как у fputcsv, свежие первыми). Чужое раскрытие — 404.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterator
from typing import Any

import pytest

from savdex import laravel_session

from .factories import Выражение, компания, открытие_контакта
from .pg_admin import sql, нужна_база, свежая_база
from .test_web_forms import SID, ТОКЕН, отправить, учётка
from .test_web_session import СЕССИЯ, завести, кука
from .web_site import адрес, открыть

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    c = компания(slug="buyer")
    t = компания(slug="target", name="ООО «Цемент; Трейд»")

    for вид, значение, главный in (
        ("phone", "+998 90 111-22-33", False),
        ("email", "sale@cement.uz", True),
    ):
        sql(
            "insert into company_contacts (company_id, type, value, is_public, is_primary, "
            "created_at, updated_at) values (%s, %s, %s, true, %s, now(), now())",
            [t, вид, значение, главный],
        )

    # Кавычки в названии — после обратной косой (escape у fputcsv)
    t2 = компания(slug="target-2", name='Бетон \\"Юг\\" сервис')
    o = компания(slug="other-buyer")

    for i, (кто, кого, заметка) in enumerate(
        [(c, t, "Первый"), (c, t2, 'Второй "важный"'), (o, t, "Чужой")]
    ):
        открытие_контакта(
            company_id=кто,
            target_company_id=кого,
            note=заметка,
            status="new",
            created_at=Выражение(f"now() - interval '{3 - i} days'"),
        )

    with адрес() as root:
        yield root


def покупатель() -> int:
    cid = int(sql("select id from companies where slug = 'buyer'")[0][0])

    return учётка("buyer@savdex.uz", company_id=cid)


def раскрытия(slug: str = "buyer") -> list[int]:
    return [
        int(r[0])
        for r in sql(
            "select u.id from contact_unlocks u join companies c on c.id = u.company_id "
            "where c.slug = %s order by u.id",
            [slug],
        )
    ]


def сброс(жалоба: bool = False) -> Callable[[], None]:
    def run() -> None:
        sql(
            "update contact_unlocks set status = 'new', note = 'Первый', complaint_status = %s, "
            "complaint_reason = null, complained_at = null, "
            "updated_at = now() - interval '1 day' where id = %s",
            ["pending" if жалоба else None, раскрытия()[0]],
        )

    return run


def снимок() -> Any:
    return sql(
        "select status, note, complaint_status, complaint_reason, complained_at is not null, "
        "updated_at > now() - interval '1 hour' from contact_unlocks order by id"
    )


def сессия(итог: dict[str, Any]) -> dict[str, Any]:
    return dict(json.loads(итог["сессия"]["payload"]))


#: Строка снимка первого раскрытия: status, note, complaint_status,
#: complaint_reason, есть complained_at, обновлено
@pytest.mark.parametrize(
    ("body", "строка", "ошибки"),
    [
        # Заметка — без пробелов по краям
        (
            {"status": "deal", "note": "  Договорились о поставке  "},
            ("deal", "Договорились о поставке"),
            None,
        ),
        ({"status": "deal"}, ("deal", "Первый"), None),
        # Пустая заметка — null
        ({"note": ""}, ("new", None), None),
        ({"status": "Первый"}, ("new", "Первый"), ["status"]),
        ({}, ("new", "Первый"), None),
        ({"status": "boom", "note": "x" * 501}, ("new", "Первый"), ["status", "note"]),
        ({"note": ["массив"]}, ("new", "Первый"), ["note"]),
    ],
)
@pytest.mark.parametrize("prefix", ["", "/en"])
def test_статус_и_заметка(сайт, body, строка, ошибки, prefix):
    итог = отправить(
        сайт,
        f"{prefix}/cabinet/contacts/{раскрытия()[0]}",
        сброс(),
        снимок,
        uid=покупатель(),
        body=body,
        method="PATCH",
    )
    данные = сессия(итог)

    # PATCH от Inertia — 303
    assert итог["ответ"]["status"] == 303
    assert итог["ответ"]["headers"]["location"].endswith(prefix + "/cabinet/settings")
    assert итог["база"][0][:2] == строка
    # Чужие раскрытия не тронуты
    assert итог["база"][2][:2] == ("new", "Чужой")

    if ошибки is None:
        assert данные["success"] == ("Saved" if prefix else "Сохранено")
    else:
        assert sorted(данные["errors"]["default"]["messages"]) == sorted(ошибки)
        # Не сохранено — строка не обновлялась
        assert итог["база"][0][5] is False

    if body == {"note": ["массив"]} and prefix:
        assert данные["errors"]["default"]["messages"]["note"] == [
            "The note field must be a string."
        ]


@pytest.mark.parametrize(
    ("body", "жалоба", "ошибка"),
    [
        ({"reason": "Телефон не отвечает третий день подряд"}, False, None),
        ({"reason": "коротко"}, False, "Слишком коротко — модератору нужны детали для проверки"),
        ({}, False, "Опишите, что не так с контактом"),
        ({"reason": "x" * 501}, False, "reason"),
        ({"reason": "Телефон не отвечает третий день подряд"}, True, "уже"),
    ],
)
def test_жалоба(сайт, body, жалоба, ошибка):
    итог = отправить(
        сайт,
        f"/cabinet/contacts/{раскрытия()[0]}/complaint",
        сброс(жалоба),
        снимок,
        uid=покупатель(),
        body=body,
    )
    данные = сессия(итог)
    [статус, _, жалоба_, причина, когда, обновлено] = итог["база"][0]

    assert итог["ответ"]["status"] == 302

    if ошибка is None:
        assert данные["success"].startswith("Жалоба отправлена")
        assert (жалоба_, причина, когда, обновлено) == ("pending", body["reason"], True, True)
    elif ошибка == "уже":
        # Одна жалоба на раскрытие
        assert данные["error"] == "Жалоба уже отправлена и рассматривается"
        assert (жалоба_, причина, обновлено) == ("pending", None, False)
    else:
        сообщения = данные["errors"]["default"]["messages"]
        assert list(сообщения) == ["reason"]

        if ошибка != "reason":
            assert сообщения["reason"] == [ошибка]

        assert (жалоба_, причина, когда, обновлено) == (None, None, False, False)

    assert статус == "new"


def test_чужое_раскрытие_404(сайт):
    итог = отправить(
        сайт,
        f"/cabinet/contacts/{раскрытия('other-buyer')[0]}",
        lambda: None,
        снимок,
        uid=покупатель(),
        body={"status": "deal"},
        method="PATCH",
    )

    assert итог["ответ"]["status"] == 404
    assert итог["база"][2][:2] == ("new", "Чужой")


@pytest.mark.parametrize(
    ("prefix", "шапка"),
    [
        ("", "Компания;Телефоны;Почта;Объявление;Открыт;Статус;Заметка"),
        ("/en", "Company;Phones;Email;Listing;Unlocked;Status;Note"),
    ],
)
def test_выгрузка_csv(сайт, prefix, шапка):
    завести(SID, {"_token": ТОКЕН, laravel_session.LOGIN_KEY: покупатель()})
    д = открыть(сайт, f"{prefix}/cabinet/contacts/export", {СЕССИЯ: кука(СЕССИЯ, SID)})

    assert д["status"] == 200
    assert д["headers"]["content-type"] == "text/csv; charset=UTF-8"
    assert re.fullmatch(
        r"attachment; filename=savdex-contacts-\d{4}-\d\d-\d\d\.csv",
        д["headers"]["content-disposition"],
    )
    assert д["headers"]["x-ratelimit-limit"] == "10"
    assert д["body"].startswith("\ufeff")

    строки = д["body"].removeprefix("\ufeff").splitlines()
    # Свежие первыми; чужого раскрытия нет
    assert строки[0] == шапка
    assert len(строки) == 3
    # Кавычка после обратной косой не удваивается (escape у fputcsv), прочие — удваиваются
    assert строки[1].startswith('"Бетон \\"Юг\\" сервис";;;;')
    assert строки[1].endswith(';Новый;"Второй ""важный"""')
    # «;» в названии — в кавычках; телефоны с пробелами — тоже
    assert строки[2].startswith('"ООО «Цемент; Трейд»";"+998 90 111-22-33";sale@cement.uz;;')
    assert строки[2].endswith(";Новый;Первый")
