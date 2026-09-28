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
    actions,
    auth,
    cabinet,
    catalog,
    chat_actions,
    companies,
    company,
    company_contact_actions,
    contact_actions,
    directory,
    home,
    it_task_actions,
    it_tasks,
    legal,
    listing,
    listing_actions,
    news,
    pricing,
    resume_actions,
    resumes,
    review_actions,
    reviews,
    settings_actions,
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
    # Формы кабинета (этап 5, шаг 21): POST, только группа forms
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?notifications/(?P<notification_id>[0-9]{1,18})/read$",
        actions.notification_read,
        name="notifications.read",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?notifications/read-all$",
        actions.notifications_read_all,
        name="notifications.read-all",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?favorites/(?P<listing_id>[0-9]{1,18})$",
        actions.favorite_toggle,
        name="favorites.toggle",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/settings/notifications$",
        actions.settings_notifications,
        name="cabinet.settings.notifications",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?locale/(?P<locale>ru|uz|en|zh|tr)$",
        actions.locale_update,
        name="locale.update",
    ),
    # «Мои объявления» (этап 5, шаг 23): формы, группа forms
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/listings/bulk$",
        listing_actions.bulk,
        name="cabinet.listings.bulk",
    ),
    *[
        re_path(
            rf"^(?:(?:uz|en|zh|tr)/)?cabinet/listings/(?P<listing_id>[0-9]{{1,18}})/{verb}$",
            getattr(listing_actions, verb),
            name=f"cabinet.listings.{verb}",
        )
        for verb in ("renew", "archive", "resubmit")
    ],
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/listings/(?P<listing_id>[0-9]{1,18})$",
        listing_actions.destroy,
        name="cabinet.listings.destroy",
    ),
    # «Мои контакты» (этап 5, шаг 24): формы и выгрузка, группа forms
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/contacts/export$",
        contact_actions.export,
        name="cabinet.contacts.export",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/contacts/(?P<unlock_id>[0-9]{1,18})$",
        contact_actions.update,
        name="cabinet.contacts.update",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/contacts/(?P<unlock_id>[0-9]{1,18})/complaint$",
        contact_actions.complain,
        name="cabinet.contacts.complain",
    ),
    # IT-задачи своей компании (этап 5, шаг 27): группа forms
    *[
        re_path(
            rf"^(?:(?:uz|en|zh|tr)/)?cabinet/it-tasks/(?P<task_id>[0-9]{{1,18}})/{verb}$",
            getattr(it_task_actions, verb),
            name=f"cabinet.it-tasks.{verb}",
        )
        for verb in ("close", "complete", "reopen")
    ],
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/it-tasks/(?P<task_id>[0-9]{1,18})$",
        it_task_actions.destroy,
        name="cabinet.it-tasks.destroy",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/it-tasks/(?P<task_id>[0-9]{1,18})/files/"
        r"(?P<file_id>[0-9]{1,18})$",
        it_task_actions.destroy_file,
        name="cabinet.it-tasks.files.destroy",
    ),
    # Отклики в чат (этап 5, шаг 26): группа forms
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?listing/(?P<listing_id>[0-9]{1,18})/respond$",
        chat_actions.respond,
        name="listing.respond",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?it-services/(?P<task_id>[0-9]{1,18})/respond$",
        chat_actions.respond_task,
        name="it-tasks.respond",
    ),
    # Отзывы о своей компании (этап 5, шаг 25): ответ и спор, группа forms
    *[
        re_path(
            rf"^(?:(?:uz|en|zh|tr)/)?cabinet/reviews/(?P<review_id>[0-9]{{1,18}})/{verb}$",
            getattr(review_actions, verb),
            name=f"cabinet.reviews.{verb}",
        )
        for verb in ("reply", "dispute")
    ],
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
    re_path(r"^(?:(?:uz|en|zh|tr)/)?cabinet/resume$", resume_actions.page, name="cabinet.resume"),
    # Контакты своей компании (этап 5, шаг 31): группа forms
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/company/contacts$",
        company_contact_actions.store,
        name="cabinet.contacts.store",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/company/contacts/(?P<contact_id>[0-9]{1,18})$",
        company_contact_actions.contact,
        name="cabinet.contacts.edit",
    ),
    # Настройки профиля (этап 5, шаг 29): группа forms
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/settings/profile$",
        settings_actions.profile,
        name="cabinet.settings.profile",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/settings/telegram$",
        settings_actions.telegram,
        name="cabinet.settings.telegram",
    ),
    # Своё резюме (этап 5, шаг 28): опубликовать и скрыть, группа forms
    *[
        re_path(
            rf"^(?:(?:uz|en|zh|tr)/)?cabinet/resume/{verb}$",
            getattr(resume_actions, verb),
            name=f"cabinet.resume.{verb}",
        )
        for verb in ("publish", "hide")
    ],
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
        chat_actions.thread,
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
