"""
«Больше не присылать письма» — ссылка из письма потенциальному клиенту
(savdex/crm/prospects.py, unsubscribe_url).

Открытие ссылки ничего не меняет: почтовые сканеры в компаниях открывают
все ссылки из писем, и отписка по одному открытию отписала бы всех.
Отписывает кнопка на странице (POST) — и почтовая программа по
заголовку List-Unsubscribe-Post (одно нажатие, RFC 8058), тоже POST.
Чужой ключ — 404.
"""

from __future__ import annotations

from django.http import Http404, HttpRequest, HttpResponse, HttpResponseNotAllowed
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt

from savdex.crm import prospects
from savdex.crm.models import Prospect


@csrf_exempt
def view(request: HttpRequest, pk: str, token: str) -> HttpResponse:
    if request.method not in ("GET", "HEAD", "POST"):
        return HttpResponseNotAllowed(["GET", "POST"])

    number = int(pk)

    if request.method == "POST":
        prospect = prospects.unsubscribe(number, token)
    elif token == prospects.unsubscribe_token(number):
        prospect = Prospect.everything.filter(pk=number).first()
    else:
        prospect = None

    if prospect is None:
        raise Http404

    response = render(
        request,
        "crm/unsubscribe.html",
        {"done": prospect.unsubscribed_at is not None, "action": request.path},
    )
    response["X-Robots-Tag"] = "noindex"
    response["Cache-Control"] = "no-store"

    return response
