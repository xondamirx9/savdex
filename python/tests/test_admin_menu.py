"""
Меню админки слева: группы по работе, а не по приложениям Django.

- у суперадмина нет групп из одного пункта («Закупки» — в «Данных»,
  «Обращения» — в CRM, «Пользователи» — в «Системе»);
- каждый раздел — ровно в одной группе, порядок внутри — как в Filament;
- сотруднику видны только группы с доступными ему разделами;
- открытую группу отмечает «current», у группы нет своей страницы;
- «хлебные крошки» называют группу меню и ведут на всю группу
  (/py/admin/tenders/ — все «Данные»), хотя get_app_list с приложением
  по-прежнему отдаёт только его разделы, как у Django;
- меню помнит прокрутку между страницами (savdex.admin.navScroll).
"""

from __future__ import annotations

from typing import Any

from django.template.loader import render_to_string
from django.test import RequestFactory

from savdex import access
from savdex.adminsite import MENU_GROUPS, StaffUser, site


def _запрос(role: str, path: str = "/py/admin/") -> Any:
    сотрудник = access.Admin(
        id=1,
        name="Сотрудник",
        email=f"{role}@savdex.uz",
        is_admin=True,
        role=role,
        status="active",
    )
    request = RequestFactory().get(path)
    request.admin = сотрудник  # type: ignore[attr-defined]
    request.user = StaffUser(сотрудник)  # type: ignore[assignment]

    return request


def _меню(role: str, path: str = "/py/admin/") -> dict[str, list[str]]:
    return {
        group["name"]: [model["object_name"] for model in group["models"]]
        for group in site.get_app_list(_запрос(role, path))
    }


def test_у_суперадмина_нет_групп_из_одного_пункта():
    меню = _меню("superadmin")

    assert list(меню) == [
        "CRM",
        "Модерация",
        "Данные",
        "Монетизация",
        "Контент",
        "Справочники",
        "Система",
    ]
    assert all(len(разделы) > 1 for разделы in меню.values()), меню
    assert меню["Данные"][-1] == "Tender"
    assert "Ticket" in меню["CRM"] and меню["CRM"][-1] == "Stage"
    assert меню["Модерация"].index("Complaint") > меню["Модерация"].index("CompanyDocument")
    assert меню["Система"][:2] == ["User", "StaffMember"]
    # «Возвраты» после «Счетов и оплат», как в Filament (8e32f2a)
    assert меню["Монетизация"].index("Payment") < меню["Монетизация"].index("Refund")


def test_каждый_раздел_ровно_в_одной_группе():
    в_группах = [key for _, _, keys in MENU_GROUPS for key in keys]
    зарегистрированы = {
        f"{model._meta.app_label}.{model._meta.model_name}" for model in site._registry
    }

    assert len(в_группах) == len(set(в_группах))
    assert set(в_группах) == зарегистрированы


def test_сотруднику_только_свои_группы():
    модератор = _меню("moderator")

    assert list(модератор) == ["CRM", "Модерация", "Данные", "Справочники"]
    # Доски лидов и сделок — смотреть; этапы воронки правят администраторы
    assert модератор["CRM"] == ["Lead", "Deal"]
    assert "Complaint" in модератор["Модерация"]
    assert "Tender" in модератор["Данные"]


def test_открытая_группа():
    request = _запрос("superadmin", "/py/admin/tenders/tender/5/change/")
    группы = {group["name"]: group for group in site.get_app_list(request)}

    assert группы["Данные"]["current"] is True
    assert not any(g["current"] for name, g in группы.items() if name != "Данные")
    assert группы["Данные"]["app_url"] == ""

    html = render_to_string(
        "admin/nav_sidebar.html",
        {"available_apps": list(группы.values()), "request": request},
    )
    assert "app-data module current-app" in html
    assert '<span class="section">Данные</span>' in html
    assert "Models in the" not in html, "у группы нет своей страницы — заголовок без ссылки"
    assert 'class="model-tender current-model"' in html
    assert "savdex.admin.navScroll" in html


def test_страница_приложения_как_у_django():
    [гео] = site.get_app_list(_запрос("superadmin", "/py/admin/geo/"), "geo")

    assert гео["app_label"] == "geo"
    assert гео["app_url"] == "/py/admin/geo/"
    assert [model["object_name"] for model in гео["models"]] == ["Country", "City"]


def test_крошки_ведут_на_всю_группу(monkeypatch):
    monkeypatch.setattr(site, "each_context", lambda request: {})

    ответ = site.app_index(_запрос("superadmin", "/py/admin/tenders/"), "tenders")
    [группа] = ответ.context_data["app_list"]

    assert ответ.context_data["title"] == "Данные"
    assert [model["object_name"] for model in группа["models"]] == [
        "CompanyRecord",
        "Listing",
        "ItTask",
        "Tender",
    ]


def test_многострочных_комментариев_в_шаблонах_нет():
    """
    Комментарий-решётка у Django однострочный: многострочный печатается
    на странице как есть (так в шапку админки попал текст о переходах).
    """
    from pathlib import Path

    шаблоны = Path(__file__).resolve().parents[1] / "savdex" / "templates"
    плохие = [
        f"{path.relative_to(шаблоны)}:{номер}"
        for path in шаблоны.rglob("*.html")
        for номер, строка in enumerate(path.read_text(encoding="utf-8").splitlines(), 1)
        if "{#" in строка and "#}" not in строка.split("{#", 1)[1]
    ]

    assert плохие == []
