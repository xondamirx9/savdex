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

from savdex import adminlogin, adminpanel, adminsite, visitor
from savdex.crm import unsubscribe as prospect_unsubscribe
from savdex.data.meyos import feed as meyos_feed
from savdex.web import (
    account_actions,
    actions,
    auth,
    auth_actions,
    billing,
    billing_actions,
    cabinet,
    catalog,
    chat_actions,
    companies,
    company,
    company_contact_actions,
    company_file_actions,
    company_info_actions,
    company_profile_actions,
    contact_actions,
    directory,
    downloads,
    fallback,
    home,
    it_task_actions,
    it_tasks,
    legal,
    listing,
    listing_actions,
    listing_image_actions,
    microsite,
    news,
    og_image,
    onboarding_actions,
    payment_callbacks,
    pricing,
    promo_actions,
    register_code,
    resume_actions,
    resumes,
    review_actions,
    reviews,
    seo_files,
    services,
    settings_actions,
    site_actions,
    telegram_webhook,
    tenders,
    unlock_actions,
    wizard_actions,
)
from savdex.web import views as web


def up(request: HttpRequest) -> HttpResponse:
    """То же, что /up у Laravel."""
    return HttpResponse("ok", content_type="text/plain")


urlpatterns = [
    path("up", up),
    path("py/up", up),
    # Пропуск из Laravel (savdex/bridge.py) — пункты меню оставшегося Filament
    path("py/login", adminpanel.login),
    path("py/logout", adminpanel.logout),
    # Вход и выход админки (шаг 67): раньше разделов Django — свои виды,
    # а не django.contrib.auth; без посредника входа (AdminMiddleware)
    path("py/admin/login/", adminlogin.login_page, name="savdex_admin_login"),
    # Бывшая панель Filament (этап 8): /admin… — в админку Django,
    # служебные адреса Livewire и Filament — 404
    re_path(r"^admin(?:/(?P<rest>.*))?$", fallback.admin, name="filament.redirect"),
    re_path(r"^(?:livewire-[0-9a-f]+|livewire|filament)(?:/(?P<rest>.*))?$", fallback.gone),
    path("py/admin/", adminsite.site.urls),
    # Кто вошёл на сайт — по сессии Laravel (этап 3, savdex/visitor.py)
    path("py/whoami", visitor.whoami),
    # Страницы сайта (этап 3, savdex/web/); с этапа 8 Apache передаёт сюда
    # всё, кроме готовых файлов (docker/apache-python.conf)
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
        r"^(?:(?:uz|en|zh|tr)/)?services/(?P<slug>it|hr|recruitment|logistics|customs|accounting)$",
        services.show,
        name="services.show",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?it-services/(?P<slug>[^/]+)$", it_tasks.show, name="it-tasks.show"
    ),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?companies$", companies.index, name="companies.index"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?company/(?P<slug>[^/]+)$", company.show, name="companies.show"),
    # Скачивание файлов с приватного диска (этап 5, шаг 44)
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?files/(?P<document_id>[0-9]{1,18})$",
        downloads.company_file,
        name="files.download",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?it-services/files/(?P<file_id>[0-9]{1,18})$",
        downloads.it_task_file,
        name="it-tasks.file",
    ),
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
        it_task_actions.task,
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
    # Мастер объявления (этап 5, шаг 38): новый черновик и публикация, группа forms
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/listings/create$",
        wizard_actions.create,
        name="cabinet.listings.create",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/listings/(?P<listing_id>[0-9]{1,18})/publish$",
        wizard_actions.publish,
        name="cabinet.listings.publish",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/listings/(?P<listing_id>[0-9]{1,18})/autosave$",
        wizard_actions.autosave,
        name="cabinet.listings.autosave",
    ),
    # Раскрытие контактов на визитке (этап 5, шаг 40): группа forms
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?company/(?P<slug>[^/]+)/unlock$",
        unlock_actions.unlock,
        name="companies.unlock",
    ),
    # Отзыв о компании на визитке (этап 5, шаг 41): группа forms
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?company/(?P<slug>[^/]+)/review$",
        review_actions.store,
        name="companies.review",
    ),
    # Фото объявления (этап 5, шаг 37): группа forms
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/listings/(?P<listing_id>[0-9]{1,18})/images$",
        listing_image_actions.store,
        name="cabinet.listings.images.store",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/listings/(?P<listing_id>[0-9]{1,18})/images/"
        r"(?P<image_id>[0-9]{1,18})$",
        listing_image_actions.destroy,
        name="cabinet.listings.images.destroy",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/listings/(?P<listing_id>[0-9]{1,18})/images/"
        r"(?P<image_id>[0-9]{1,18})/cover$",
        listing_image_actions.cover,
        name="cabinet.listings.images.cover",
    ),
    # Вход, регистрация и пароль (этап 5): страницы, открываемые GET-запросом
    # Вход и выход: GET — страница, POST — форма (этап 5, шаг 45, группа forms)
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?login$",
        auth_actions.either(auth.login, auth_actions.login),
        name="login",
    ),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?logout$", auth_actions.logout, name="logout"),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?register$",
        auth_actions.either(auth.register, auth_actions.register),
        name="register",
    ),
    # Шаги регистрации: почта, код из письма, анкета (шаг 69)
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?register/email$",
        register_code.send_code,
        name="register.email",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?register/code$",
        auth_actions.either(register_code.code_page, register_code.confirm_code),
        name="register.code",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?register/code/resend$",
        register_code.resend_code,
        name="register.code.resend",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?register/details$",
        register_code.details,
        name="register.details",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?forgot-password$",
        auth_actions.either(auth.forgot_password, account_actions.forgot_password),
        name="password.request",
    ),
    # Пароль и почта: формы (этап 5, шаг 46, группа forms)
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?reset-password$",
        account_actions.reset_password,
        name="password.update",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?verify-email/code$",
        account_actions.verify_code,
        name="verification.code",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?email/verification-notification$",
        account_actions.verify_send,
        name="verification.send",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?verify-email/(?P<user_id>[^/]+)/(?P<digest>[^/]+)$",
        account_actions.verify_link,
        name="verification.verify",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?reset-password/(?P<token>[^/]+)$",
        auth.reset_password,
        name="password.reset",
    ),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?verify-email$", auth.verify_email, name="verification.notice"),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?password/change$",
        auth_actions.either(auth.force_password, account_actions.force_password),
        name="password.forced",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?onboarding/company$",
        auth_actions.either(auth.onboarding_company, onboarding_actions.company),
        name="onboarding.company",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?onboarding/skip$",
        onboarding_actions.skip,
        name="onboarding.skip",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?reviews/new$",
        auth_actions.either(auth.review_new, onboarding_actions.review),
        name="reviews.create",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/settings/company-info$",
        company_info_actions.info,
        name="cabinet.settings.company",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/settings/company-info/support$",
        company_info_actions.support,
        name="cabinet.settings.company.support",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/settings/delete$",
        account_actions.delete_account,
        name="cabinet.settings.destroy",
    ),
    # Кабинет (этап 5): страницы, открываемые GET-запросом
    re_path(r"^(?:(?:uz|en|zh|tr)/)?cabinet$", cabinet.dashboard, name="cabinet"),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/analytics$", cabinet.analytics, name="cabinet.analytics"
    ),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?cabinet/incoming$", cabinet.incoming, name="cabinet.incoming"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?cabinet/listings$", cabinet.listings, name="cabinet.listings"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?cabinet/chats$", cabinet.chats, name="cabinet.chats"),
    # Продвижение: GET — страница, POST — запуск (этап 5, шаг 44, группа forms)
    re_path(r"^(?:(?:uz|en|zh|tr)/)?cabinet/promo$", promo_actions.page, name="cabinet.promo"),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?cabinet/resume$", resume_actions.page, name="cabinet.resume"),
    # Файлы своей компании (этап 5, шаг 42): группа forms
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/company/files$",
        company_file_actions.store,
        name="cabinet.company.files.store",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/company/files/(?P<document_id>[0-9]{1,18})$",
        company_file_actions.document,
        name="cabinet.company.files.update",
    ),
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
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/settings/categories$",
        settings_actions.categories,
        name="cabinet.settings.categories",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/settings/telegram-feed$",
        settings_actions.telegram_feed,
        name="cabinet.settings.telegram_feed",
    ),
    # Своё резюме (этап 5, шаг 28): опубликовать и скрыть, группа forms
    *[
        re_path(
            rf"^(?:(?:uz|en|zh|tr)/)?cabinet/resume/{verb}$",
            getattr(resume_actions, verb),
            name=f"cabinet.resume.{verb}",
        )
        for verb in ("publish", "hide", "photo")
    ],
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/company$",
        company_profile_actions.page,
        name="cabinet.company",
    ),
    # Логотип и обложка компании (этап 5, шаг 34): группа forms
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/company/logo$",
        company_profile_actions.logo,
        name="cabinet.company.logo",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/company/cover$",
        company_profile_actions.cover,
        name="cabinet.company.cover",
    ),
    # IT-задачи: GET — список, POST — новая задача (этап 5, шаг 43, группа forms)
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/it-tasks$",
        it_task_actions.tasks,
        name="cabinet.it-tasks",
    ),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?cabinet/site$", site_actions.page, name="cabinet.site"),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/billing$", billing.billing_page, name="cabinet.billing"
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/billing/invoice/(?P<payment_id>[0-9]{1,18})$",
        billing.invoice,
        name="cabinet.billing.invoice",
    ),
    # Формы кассы (этап 7, шаг 53): группа forms
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/billing/order$",
        billing_actions.order,
        name="cabinet.billing.order",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/billing/promo$",
        billing_actions.promo,
        name="cabinet.billing.promo",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/billing/invoice/(?P<payment_id>[0-9]{1,18})/pay$",
        billing_actions.pay,
        name="cabinet.billing.invoice.pay",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/billing/cancel$",
        billing_actions.cancel,
        name="cabinet.billing.cancel",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/billing/resume$",
        billing_actions.resume,
        name="cabinet.billing.resume",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/billing/card/(?P<card_id>[0-9]{1,18})$",
        billing_actions.remove_card,
        name="cabinet.billing.card.remove",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/billing/invoice/(?P<payment_id>[0-9]{1,18})/cancel$",
        billing_actions.cancel_invoice,
        name="cabinet.billing.invoice.cancel",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/site/preview$",
        microsite.preview,
        name="cabinet.site.preview",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?s/(?P<subdomain>[a-z0-9-]+)$", microsite.page, name="microsite.page"
    ),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?robots\.txt$", seo_files.robots, name="robots"),
    # Постоянная ссылка для MEYOS: мебельные объявления в JSON (savdex/data/meyos.py)
    re_path(r"^feeds/meyos\.json$", meyos_feed, name="feeds.meyos"),
    # «Больше не присылать письма» из рассылки потенциальным клиентам
    # (savdex/crm/unsubscribe.py)
    re_path(
        r"^unsubscribe/(?P<pk>[0-9]{1,18})/(?P<token>[0-9a-f]{32})$",
        prospect_unsubscribe.view,
        name="prospects.unsubscribe",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?og/listing/(?P<listing_id>[0-9]{1,18})\.jpg$",
        og_image.listing,
        name="og.listing",
    ),
    re_path(r"^(?:(?:uz|en|zh|tr)/)?sitemap\.xml$", seo_files.sitemap, name="sitemap"),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?sitemap-(?P<part>[a-z0-9-]+)\.xml$",
        seo_files.sitemap_part,
        name="sitemap.part",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?telegram/webhook/(?P<secret>[A-Za-z0-9_-]{8,64})$",
        telegram_webhook.webhook,
        name="telegram.webhook",
    ),
    # Колбэки шлюза Uzum (этап 7, шаг 54): группа payments. Merchant API —
    # раньше общего вебхука, как у Laravel
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?payments/uzum/callback/(?P<operation>[a-z]+)$",
        payment_callbacks.merchant,
        name="payments.uzum.operation",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?payments/(?P<provider>[a-z]+)/callback(?:/(?P<operation>[a-z]+))?$",
        payment_callbacks.webhook,
        name="payments.callback",
    ),
    # Мини-сайт (этап 5, шаг 35): публикация и фон, группа forms
    *[
        re_path(
            rf"^(?:(?:uz|en|zh|tr)/)?cabinet/site/{verb}$",
            getattr(site_actions, verb),
            name=f"cabinet.site.{verb}",
        )
        for verb in ("publish", "unpublish")
    ],
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/site/hero$", site_actions.hero, name="cabinet.site.hero"
    ),
    # Товары мини-сайта (этап 5, шаг 36): группа forms
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/site/products$",
        site_actions.product_store,
        name="cabinet.site.products.store",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/site/products/(?P<product_id>[0-9]{1,18})$",
        site_actions.product,
        name="cabinet.site.products.update",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/listings/(?P<listing_id>[0-9]{1,18})/edit$",
        cabinet.listing_wizard,
        name="cabinet.listings.edit",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/chats/(?P<thread_id>[0-9]{1,18})$",
        chat_actions.thread,
        name="cabinet.chats.show",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/it-tasks/create$",
        cabinet.it_task_create,
        name="cabinet.it-tasks.create",
    ),
    re_path(
        r"^(?:(?:uz|en|zh|tr)/)?cabinet/it-tasks/(?P<task_id>[0-9]{1,18})/edit$",
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
    # Последним: всё, у чего нет маршрута, — страница 404 сайта, а не
    # отладочная Django (этап 8: Laravel за спиной больше нет)
    re_path(r"^.*$", fallback.page_not_found, name="fallback.404"),
]

# Несовпавший адрес и ошибка сервера — страница в оформлении сайта (этап 8)
handler404 = "savdex.web.fallback.page_not_found"
handler500 = "savdex.web.fallback.server_error"
