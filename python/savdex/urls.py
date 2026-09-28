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
from savdex.web import (
    auth,
    cabinet,
    catalog,
    companies,
    company,
    directory,
    home,
    it_tasks,
    legal,
    listing,
    news,
    pricing,
    resumes,
    reviews,
    tenders,
)
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
    re_path(r"^(?:(?:uz|en|zh|tr)/?)?$", home.home, name="home"),
    *[
        re_path(rf"^(?:(?:uz|en|zh|tr)/)?(?P<key>{key})$", web.doc, name=f"docs.{key}")
        for key in ("help", "guide", "rules")
    ],
    re_path(r"^(?:(?:uz|en|zh|tr)/)?about$", web.about, name="about"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?contact$", web.contacts, name="contacts"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?pricing$", pricing.pricing, name="pricing"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?reviews$", reviews.index, name="reviews"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?resumes$", resumes.index, name="resumes"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?resume/(?P<slug>[^/]+)$", resumes.show, name="resumes.show"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?it-services$", it_tasks.index, name="it-tasks"),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?it-services/(?P<slug>[^/]+)$", it_tasks.show, name="it-tasks.show"
    ),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?companies$", companies.index, name="companies.index"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?company/(?P<slug>[^/]+)$", company.show, name="companies.show"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?catalog$", catalog.catalog, name="catalog"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?listing/(?P<slug>[^/]+)$", listing.show, name="listings.show"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?tenders/(?P<slug>[^/]+)$", tenders.show, name="tenders.show"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?countries$", directory.countries, name="countries"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?partners$", directory.partners, name="partners"),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?partners/(?P<tier>general|regular|multi)$",
        directory.partners_tier,
        name="partners-tier",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?countries/(?P<code>[A-Za-z]{2})/companies$",
        directory.country_companies,
        name="countries.companies",
    ),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?tenders$", directory.tenders_redirect, name="tenders"),
    # Вход, регистрация и пароль (этап 5): страницы, открываемые GET-запросом
    re_path(r"^(?:(?:uz|en|zh|tr)/)?login$", auth.login, name="login"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?register$", auth.register, name="register"),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?forgot-password$",
        auth.forgot_password,
        name="password.request",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?reset-password/(?P<token>[^/]+)$",
        auth.reset_password,
        name="password.reset",
    ),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?verify-email$", auth.verify_email, name="verification.notice"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?password/change$", auth.force_password, name="password.forced"),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?onboarding/company$",
        auth.onboarding_company,
        name="onboarding.company",
    ),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?reviews/new$", auth.review_new, name="reviews.create"),
    # Кабинет (этап 5): страницы, открываемые GET-запросом
    re_path(r"^(?:(?:uz|en|zh|tr)/)?cabinet$", cabinet.dashboard, name="cabinet"),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/analytics$", cabinet.analytics, name="cabinet.analytics"
    ),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?cabinet/incoming$", cabinet.incoming, name="cabinet.incoming"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?cabinet/listings$", cabinet.listings, name="cabinet.listings"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?cabinet/chats$", cabinet.chats, name="cabinet.chats"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?cabinet/promo$", cabinet.promo, name="cabinet.promo"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?cabinet/resume$", cabinet.resume, name="cabinet.resume"),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/company$", cabinet.company_page, name="cabinet.company"
    ),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?cabinet/it-tasks$", cabinet.it_tasks, name="cabinet.it-tasks"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?cabinet/site$", cabinet.site_page, name="cabinet.site"),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/listings/(?P<listing_id>[0-9]+)/edit$",
        cabinet.listing_wizard,
        name="cabinet.listings.edit",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/chats/(?P<thread_id>[0-9]+)$",
        cabinet.chat,
        name="cabinet.chats.show",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/it-tasks/create$",
        cabinet.it_task_create,
        name="cabinet.it-tasks.create",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/it-tasks/(?P<task_id>[0-9]+)/edit$",
        cabinet.it_task_edit,
        name="cabinet.it-tasks.edit",
    ),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?cabinet/reviews$", cabinet.reviews, name="cabinet.reviews"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?cabinet/contacts$", cabinet.contacts, name="cabinet.contacts"),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/settings$", cabinet.settings_page, name="cabinet.settings"
    ),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?notifications$", cabinet.notifications, name="notifications"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?favorites$", cabinet.favorites, name="favorites"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?news$", news.index, name="news"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?news/(?P<slug>[^/]+)$", news.show, name="news.show"),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?(?P<doc>terms|payment|security|privacy|refunds)$",
        legal.show,
        name="legal",
    ),
]
