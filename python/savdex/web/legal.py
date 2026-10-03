"""
Юридические документы — копия LegalController.

Тексты не переписаны в Python: и Laravel, и Django читают один файл
resources/legal/documents.json, так что редакция юриста у документа
одна. Наименование оператора, почта поддержки и реквизиты
подставляются из настроек площадки.
"""

from __future__ import annotations

import json
from functools import cache
from pathlib import Path
from typing import Any, cast

from django.conf import settings
from django.http import HttpRequest, HttpResponse

from savdex.web import inertia, locales
from savdex.web.request import context
from savdex.web.seo import Seo
from savdex.web.shared import setting, settings_values

#: LegalController::DOCS
DOCS = ("terms", "payment", "security", "privacy", "refunds")

#: trim() у PHP — только эти символы, не любой пробел Unicode
_TRIM = " \t\n\r\0\x0b"


@cache
def _source() -> dict[str, Any]:
    path = Path(settings.LARAVEL_ROOT) / "resources/legal/documents.json"
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))

    return data


class _Values:
    """Подстановки LegalController: email(), legalName(), requisite()."""

    def __init__(self) -> None:
        self.values = settings_values()

    def email(self) -> str:
        return setting(self.values, "support_email", "support@savdex.uz")

    def legal_name(self) -> str:
        full = setting(self.values, "legal_full_name", "").strip(_TRIM)

        return full if full != "" else setting(self.values, "legal_name", "ООО «ANJIR-GROUP»")

    def requisite(self, label: str, key: str) -> str | None:
        value = setting(self.values, key, "").strip(_TRIM)

        return None if value == "" else f"{label}: {value}"

    def resolve(self, node: object) -> object:
        if isinstance(node, str):
            return node.replace("{legal_name}", self.legal_name()).replace("{email}", self.email())

        if isinstance(node, dict):
            if "requisite" in node:
                return self.requisite(str(node["requisite"]), str(node["setting"]))

            return {k: self.resolve(v) for k, v in node.items()}

        if isinstance(node, list):
            resolved = [self.resolve(child) for child in node]

            # Список реквизитов: незаполненные строки выпадают (array_filter)
            if any(isinstance(child, dict) and "requisite" in child for child in node):
                return [v for v in resolved if v not in (None, "", "0")]

            return resolved

        return node


def show(request: HttpRequest, doc: str) -> HttpResponse:
    """LegalController::show."""
    ctx = context(request)

    if isinstance(ctx, HttpResponse):
        return ctx

    content = cast(dict[str, Any], _Values().resolve(_source()["documents"][doc]))

    def title(d: str) -> str:
        return ctx.t(f"legal.{d}_title")

    seo = Seo(ctx.root, ctx.path.rstrip("/") or "/", ctx.locale)
    seo.title(title(doc)).description(content["intro"]).canonical(ctx.url(doc))
    # Текст документов только на русском: другие языковые версии не выдаются за переводы
    seo.locales = [locales.DEFAULT]

    return inertia.render(
        ctx,
        "Legal",
        {
            "title": title(doc),
            "intro": content["intro"],
            "preamble": content.get("preamble", []),
            "blocks": content["blocks"],
            "updatedAt": _source()["updated_at"],
            "draft": False,
            "siblings": [{"href": f"/{d}", "label": title(d), "current": d == doc} for d in DOCS],
        },
        seo,
    )
