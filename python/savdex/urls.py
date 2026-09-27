"""
Адреса Django.

На сервере Django стоит за Apache в той же службе Render: Apache
отдаёт сюда только адреса, перечисленные в docker/apache-python.conf,
а всё остальное — Laravel. Адрес приходит целиком, без обрезки
префикса, поэтому пути здесь те же, что видит посетитель.

/py/up — проверка, что Django жив именно за Apache: её дёргает
проверка образа в CI. /up — то же для прямого запуска.
"""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.urls import path, re_path

from savdex import adminpanel, adminsite, visitor
from savdex.web import directory, home, legal, news, pricing
from savdex.web import views as web


def up(request: HttpRequest) -> HttpResponse:
    """То же, что /up у Laravel."""
    return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    path("up", up),
    path("py/up", up),
    # Вход в админку на Django — по пропуску из Laravel (savdex/bridge.py)
    path("py/login", adminpanel.login),
    path("py/logout", adminpanel.logout),
    path("py/admin/", adminsite.site.urls),
    # Кто вошёл на сайт — по сессии Laravel (этап 3, savdex/visitor.py)
    path("py/whoami", visitor.whoami),
    # Страницы сайта (этап 3, savdex/web/): адрес доходит сюда, только если
    # его группа включена в SAVDEX_PY_PAGES (docker/apache-python.conf)
    re_path(r"^(?:(?:uz|en|zh|tr)/?)?$", home.home),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?(?P<key>help|guide|rules)$", web.doc),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?about$", web.about),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?contact$", web.contacts),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?pricing$", pricing.pricing),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?countries$", directory.countries),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?partners$", directory.partners),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?news$", news.index),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?news/(?P<slug>[^/]+)$", news.show),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?(?P<doc>terms|payment|security|privacy|refunds)$", legal.show),
]
