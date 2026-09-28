"""
Этап 5, шаг 2: сводка кабинета /cabinet на Django неотличима от Laravel.

Перед страницей — посредники маршрута: гость уходит на вход (адрес
запоминается в сессии, url.intended), пароль, выданный вручную, — на
смену пароля с предупреждением в сессии; XHR, ждущий JSON, — 401.
Сессия после ответа сверяется побайтно, как в test_web_session.

Сама сводка: компания и заполненность профиля (чего не хватает — на
языке страницы), показатели за 30 дней к предыдущим 30, ряды со
сглаживанием, последние события, лимиты тарифа, истекающие и черновики;
у пунктов меню — счётчики кабинета. Без компании — пустая сводка.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator

import pytest

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база
from .test_web_session import СЕССИЯ, куки_ответа, одинаково, по_сторонам
from .web_site import laravel, войти, из_django, пользователь, сверить, страница

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()

    for seeder in ("PlanSeeder", "GeoSeeder"):
        subprocess.run(
            ["php", "artisan", "db:seed", f"--class={seeder}", "--force"],
            cwd=КОРЕНЬ,
            env=ОКРУЖЕНИЕ,
            check=True,
            capture_output=True,
        )

    # Компания владельца: объявления, статистика за 70 дней, кошелёк,
    # подписка, события одной секунды, чаты, отзывы, раскрытия
    php(
        "$c = App\\Models\\Company::factory()->create(['slug' => 'owner', 'tin' => null,"
        "'address' => '  ', 'description' => str_repeat('а', 99), 'logo_path' => null]);"
        "$other = App\\Models\\Company::factory()->create();"
        "$ls = App\\Models\\Listing::factory()->count(3)->create(['company_id' => $c->id,"
        "'expires_at' => now()->addDays(3)]);"
        "App\\Models\\Listing::factory()->create(['company_id' => $c->id,"
        "'expires_at' => now()->addDays(20)]);"
        "App\\Models\\Listing::factory()->draft()->create(['company_id' => $c->id]);"
        "$gone = App\\Models\\Listing::factory()->create(['company_id' => $c->id]);"
        "foreach (range(0, 69) as $d) { foreach ([$ls[0], $ls[1], $gone] as $k => $l) {"
        " App\\Models\\ListingStat::create(['listing_id' => $l->id,"
        " 'date' => today()->subDays($d), 'impressions' => ($d * 7 + $k) % 13,"
        " 'views' => ($d * 3 + $k) % 5, 'favorites' => $d % 2, 'unlocks' => ($d + $k) % 3]); } }"
        "$gone->delete();"
        "$plan = App\\Models\\Plan::where('code', '!=', 'free')->orderBy('id')->first();"
        "App\\Models\\Subscription::create(['company_id' => $c->id, 'plan_id' => $plan->id,"
        "'status' => 'active', 'started_at' => now()->subDays(3),"
        "'ends_at' => now()->addDays(27)]);"
        "App\\Models\\Wallet::create(['company_id' => $c->id, 'credits' => 4, 'promo_units' => 1,"
        "'contacts_used_this_period' => 2, 'period_resets_at' => now()->addDays(10)]);"
        "foreach (range(1, 7) as $i) { App\\Models\\ActivityEvent::create(["
        "'company_id' => $c->id, 'type' => 'view', 'tone' => 'primary',"
        "'message' => 'Событие '.$i, 'url' => '/cabinet']); }"
        "App\\Models\\ActivityEvent::query()->update(['created_at' => now()->subHours(3)]);"
        "App\\Models\\ContactUnlock::factory()->create(['company_id' => $c->id,"
        "'target_company_id' => $other->id]);"
        "foreach ([$other, App\\Models\\Company::factory()->create()] as $from) {"
        " App\\Models\\ContactUnlock::factory()->create(['company_id' => $from->id,"
        " 'target_company_id' => $c->id]); }"
        "$cities = App\\Models\\City::orderBy('id')->limit(2)->pluck('id');"
        "$other->update(['city_id' => $cities[1]]);"
        "App\\Models\\Review::factory()->create(['company_id' => $c->id,"
        "'author_company_id' => $other->id, 'status' => 'published']);"
        "$t = App\\Models\\MessageThread::create(['buyer_company_id' => $other->id,"
        "'seller_company_id' => $c->id]);"
        "$t->forceFill(['seller_read_at' => now()->subDay()])->save();"
        "App\\Models\\Message::create(['thread_id' => $t->id, 'company_id' => $other->id,"
        "'body' => 'Здравствуйте']);"
        # Аналитика: поисковые запросы (равные показы — порядок по запросу),
        # города компаний, открывавших контакты
        "foreach (['цемент', 'арматура', 'бетон', 'кирпич'] as $i => $q) {"
        " foreach ([0, 5, 40] as $d) { App\\Models\\SearchHit::create(['company_id' => $c->id,"
        " 'query' => $q, 'date' => today()->subDays($d), 'impressions' => 3 - ($i % 2),"
        " 'clicks' => $i]); } }"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )

    with laravel() as root:
        yield root


def владелец(сайт: str) -> dict[str, str]:
    email = "owner@savdex.uz"

    if not sql("select 1 from users where email = %s", [email]):
        пользователь(email)
        sql(
            "update users set company_id = (select id from companies where slug = 'owner') "
            "where email = %s",
            [email],
        )

    # Язык из адреса прошлой сверки (/uz/cabinet) уводил бы на /uz/…
    sql("update users set locale = 'ru' where email = %s", [email])

    return войти(сайт, email)


# ── Посредники ──────────────────────────────────────────────────────


@pytest.mark.parametrize("path", ["/cabinet", "/uz/cabinet", "/cabinet?tab=x&a=1"])
def test_гость_уходит_на_вход(сайт, path):
    стороны = по_сторонам(сайт, path, lambda: None)
    итог = одинаково(стороны)

    assert стороны["django"][0]["status"] == 302
    assert '"url":{"intended":' in итог["payload"] and '"locale"' not in итог["payload"]


def test_xhr_гостя_тоже_на_вход(сайт):
    """JSON с 401 у Laravel — только для api/*: XHR страницы уходит на вход."""
    стороны = по_сторонам(
        сайт,
        "/cabinet",
        lambda: None,
        headers={"X-Requested-With": "XMLHttpRequest", "Accept": "*/*"},
    )
    итог = одинаково(стороны)

    assert стороны["django"][0]["status"] == 302
    assert "intended" in итог["payload"]


def test_выданный_пароль_уводит_на_смену(сайт):
    пользователь("temp@savdex.uz", must_change_password=True)
    куки = войти(сайт, "temp@savdex.uz")
    sid_cookie = {СЕССИЯ: куки[СЕССИЯ]}

    стороны = по_сторонам(сайт, "/cabinet", lambda: None, cookies={**куки, **sid_cookie})
    итог = одинаково(стороны)

    assert стороны["django"][0]["headers"]["location"].endswith("/password/change")
    assert '"warning":' in итог["payload"] and '"new":["warning"]' not in итог["payload"]


# ── Сводка ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("path", ["/cabinet", "/en/cabinet", "/uz/cabinet"])
def test_сводка(сайт, path):
    куки = владелец(сайт)
    д, _ = сверить(сайт, path, куки)
    props = страница(д["body"])["props"]

    assert props["counts"] == {
        "listings": 4,
        "contacts": 1,
        "incoming": 2,
        "reviews": 1,
        "chats": 1,
    }
    assert props["expiring"] == 3 and props["drafts"] == 1
    assert len(props["events"]) == 5
    assert props["metrics"]["impressions"]["delta"] is not None


def test_без_компании(сайт):
    пользователь("nocompany@savdex.uz")
    д, _ = сверить(сайт, "/cabinet", войти(сайт, "nocompany@savdex.uz"))
    props = страница(д["body"])["props"]

    assert props["company"] is None and props["counts"] is None


def test_счётчики_только_в_кабинете(сайт):
    д, _ = сверить(сайт, "/about", владелец(сайт))

    assert страница(д["body"])["props"]["counts"] is None


def test_переход_inertia(сайт):
    куки = владелец(сайт)
    полная = из_django(сайт, "/cabinet", куки)
    версия = страница(полная["body"])["version"]

    сверить(
        сайт,
        "/cabinet",
        куки,
        headers={
            "X-Inertia": "true",
            "X-Inertia-Version": версия,
            "X-Requested-With": "XMLHttpRequest",
        },
    )
    assert куки_ответа(полная)[СЕССИЯ]["value"]


# ── Аналитика ───────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "query",
    ["", "?period=7", "?period=90", "?period=abc", "?period=", "?period[]=7", "?period=7abc"],
)
def test_аналитика(сайт, query):
    сверить(сайт, "/cabinet/analytics" + query, владелец(сайт))


@pytest.mark.parametrize("path", ["/uz/cabinet/analytics?period=90", "/en/cabinet/analytics"])
def test_аналитика_расширенная(сайт, path):
    """Тариф с расширенной аналитикой: запросы и сравнение с категорией."""
    sql(
        "update subscriptions set plan_id = (select id from plans where advanced_analytics "
        "order by id limit 1) where company_id = (select id from companies where slug = 'owner')"
    )
    д, _ = сверить(сайт, path, владелец(сайт))
    props = страница(д["body"])["props"]

    assert props["advanced"] is True and props["queries"] and props["benchmark"]


def test_аналитика_без_компании(сайт):
    пользователь("nocompany2@savdex.uz")
    сверить(сайт, "/cabinet/analytics", войти(сайт, "nocompany2@savdex.uz"))


# ── Кто мной интересуется ───────────────────────────────────────────


def _просмотры() -> None:
    """Просмотры визитки и объявлений: зрители, удалённое объявление, «и ещё»."""
    if sql("select 1 from audience_views limit 1"):
        return

    [(owner,)] = sql("select id from companies where slug = 'owner'")
    зрители = [r[0] for r in sql("select id from companies where id != %s order by id", [owner])]
    объявления = [
        r[0] for r in sql("select id from listings where company_id = %s order by id", [owner])
    ]

    for i, зритель in enumerate(зрители[:3]):
        for j, объявление in enumerate([None, *объявления][: 2 + 2 * i]):
            sql(
                "insert into audience_views (target_company_id, viewer_company_id, listing_id, "
                "created_at, updated_at) values (%s, %s, %s, "
                "now() - make_interval(hours => %s + 1), now())",
                [owner, зритель, объявление, i + j],
            )

    # Раскрытия — часами раньше: «N секунд назад» разошлось бы между сторонами
    sql("update contact_unlocks set created_at = now() - make_interval(hours => id::int)")

    # Старше месяца — не считается
    sql(
        "insert into audience_views (target_company_id, viewer_company_id, listing_id, "
        "created_at, updated_at) values (%s, %s, null, now() - interval '40 days', now())",
        [owner, зрители[0]],
    )


@pytest.mark.parametrize("names", [False, True])
@pytest.mark.parametrize("path", ["/cabinet/incoming", "/uz/cabinet/incoming"])
def test_кто_интересуется(сайт, path, names):
    _просмотры()
    sql(
        "update subscriptions set plan_id = (select id from plans where sees_interested_names = %s "
        "order by id limit 1) where company_id = (select id from companies where slug = 'owner')",
        [names],
    )
    д, _ = сверить(сайт, path, владелец(сайт))
    props = страница(д["body"])["props"]

    assert props["sees_names"] is names and props["viewers"] and props["rows"]


def test_кто_интересуется_без_компании(сайт):
    пользователь("nocompany3@savdex.uz")
    сверить(сайт, "/cabinet/incoming", войти(сайт, "nocompany3@savdex.uz"))


# ── Отзывы ──────────────────────────────────────────────────────────


def _отзывы() -> None:
    """Отзывы разных оценок: критерии с нулями и пустыми, автор в корзине, спор."""
    if sql("select count(*) from reviews")[0][0] > 1:
        return

    php(
        "$c = App\\Models\\Company::where('slug', 'owner')->first();"
        "$l = $c->listings()->orderBy('id')->first();"
        "foreach ([[5, 5, 0, null, 4], [3, 2, 3, 3, 3], [4, 4, 5, null, null], [5, 5, 5, 5, 5]]"
        " as $i => [$r, $d, $s, $t, $q]) { $a = App\\Models\\Company::factory()->create();"
        " App\\Models\\Review::factory()->create(['company_id' => $c->id,"
        " 'author_company_id' => $a->id, 'rating' => $r, 'rating_description' => $d,"
        " 'rating_response' => $s, 'rating_deadlines' => $t, 'rating_quality' => $q,"
        " 'status' => 'published', 'listing_id' => $i === 0 ? $l->id : null,"
        " 'reply' => $i === 1 ? 'Спасибо' : null, 'dispute_status' => $i === 2 ? 'rejected' : null,"
        " 'moderator_note' => $i === 2 ? 'Отзыв по делу' : null,"
        " 'deal_confirmed' => $i % 2 === 0]);"
        " if ($i === 3) { $a->delete(); } }"
        "App\\Models\\Review::factory()->create(['company_id' => $c->id,"
        "'author_company_id' => App\\Models\\Company::factory()->create()->id,"
        "'status' => 'hidden']);"
        "echo 'ok';"
    )
    # Часами раньше, одна пара — в одну секунду: «N секунд назад» и
    # порядок равных не плавают
    sql("update reviews set created_at = now() - make_interval(hours => id::int)")
    sql(
        "update reviews set created_at = (select min(created_at) from reviews) where id in "
        "(select id from reviews order by id desc limit 2)"
    )


@pytest.mark.parametrize("path", ["/cabinet/reviews", "/zh/cabinet/reviews"])
def test_отзывы(сайт, path):
    _отзывы()
    д, _ = сверить(сайт, path, владелец(сайт))
    props = страница(д["body"])["props"]

    assert props["summary"]["total"] == 5 and len(props["reviews"]) == 5


def test_отзывы_без_компании(сайт):
    пользователь("nocompany4@savdex.uz")
    сверить(сайт, "/cabinet/reviews", войти(сайт, "nocompany4@savdex.uz"))


# ── Мои контакты ────────────────────────────────────────────────────


def _раскрытия() -> None:
    """Раскрытия владельца: статусы, заметки, телефоны и почты, компания в корзине."""
    if sql("select count(*) from contact_unlocks where note is not null")[0][0]:
        return

    php(
        "$c = App\\Models\\Company::where('slug', 'owner')->first();"
        "$l = $c->listings()->orderBy('id')->first();"
        "foreach (['negotiating', 'deal', 'rejected', 'contacted'] as $i => $s) {"
        " $t = App\\Models\\Company::factory()->create(['name' => 'Поставщик '.$i]);"
        " $t->contacts()->create(['type' => 'phone', 'value' => '+99890000000'.$i,"
        " 'is_public' => true, 'is_primary' => $i === 1]);"
        " $t->contacts()->create(['type' => 'email', 'value' => 'p'.$i.'@x.uz',"
        " 'is_public' => false]);"
        " $t->contacts()->create(['type' => 'phone', 'value' => '+99871000000'.$i,"
        " 'is_public' => true]);"
        " App\\Models\\ContactUnlock::factory()->create(['company_id' => $c->id,"
        " 'target_company_id' => $t->id, 'status' => $s, 'note' => $i === 2 ? 'ждём КП' : null,"
        " 'listing_id' => $i === 0 ? $l->id : null,"
        " 'complaint_status' => $i === 3 ? 'pending' : null]);"
        " if ($i === 3) { $t->delete(); } }"
        "echo 'ok';"
    )
    sql("update contact_unlocks set created_at = now() - make_interval(hours => id::int)")


@pytest.mark.parametrize(
    "query",
    [
        "",
        "?status=deal",
        "?status=nonsense",
        "?q=%D0%9F%D0%BE%D1%81%D1%82%D0%B0%D0%B2%D1%89%D0%B8%D0%BA",
        "?q=%D0%9A%D0%9F",
        "?q=%20%20&status=",
        "?q=%25",
    ],
)
def test_мои_контакты(сайт, query):
    _раскрытия()
    сверить(сайт, "/cabinet/contacts" + query, владелец(сайт))


def test_мои_контакты_без_компании(сайт):
    пользователь("nocompany5@savdex.uz")
    сверить(сайт, "/cabinet/contacts", войти(сайт, "nocompany5@savdex.uz"))


# ── Настройки ───────────────────────────────────────────────────────


def test_настройки(сайт):
    куки = владелец(сайт)
    [(uid,)] = sql("select id from users where email = 'owner@savdex.uz'")
    sql(
        "update users set phone = '+998901112233', last_login_at = '2026-09-20 08:05:00', "
        "last_login_ip = '10.1.2.3', telegram_username = 'owner_tg', company_role = 'owner' "
        "where id = %s",
        [uid],
    )
    sql("delete from notification_preferences where user_id = %s", [uid])
    sql(
        "insert into notification_preferences (user_id, event, email, telegram, created_at, "
        "updated_at) values (%s, 'new_review', false, true, now(), now()), "
        "(%s, 'digest', true, false, now(), now()), (%s, 'unknown', false, false, now(), now())",
        [uid, uid, uid],
    )

    for path in ("/cabinet/settings", "/tr/cabinet/settings"):
        сверить(сайт, path, куки)


def test_настройки_без_компании(сайт):
    пользователь("nocompany6@savdex.uz")
    сверить(сайт, "/cabinet/settings", войти(сайт, "nocompany6@savdex.uz"))


# ── Уведомления ─────────────────────────────────────────────────────


@pytest.mark.parametrize("query", ["", "?filter=unread", "?filter=other", "?filter="])
def test_уведомления(сайт, query):
    куки = владелец(сайт)
    [(uid,)] = sql("select id from users where email = 'owner@savdex.uz'")

    if not sql("select 1 from user_notifications where user_id = %s", [uid]):
        for i in range(7):
            sql(
                "insert into user_notifications (user_id, type, tone, title, body, url, "
                "is_broadcast, read_at, created_at, updated_at) values (%s, %s, 'primary', %s, "
                "%s, %s, %s, %s, now() - make_interval(hours => %s), now())",
                [
                    uid,
                    "broadcast" if i < 3 else "review",
                    f"Уведомление {i}",
                    "Текст" if i % 2 else None,
                    "/cabinet/reviews" if i % 3 == 0 else None,
                    i < 3,
                    None if i % 2 else "2026-09-01 10:00:00",
                    # Рассылка — в одну секунду: порядок решает id
                    1 if i < 3 else i + 1,
                ],
            )

    сверить(сайт, "/notifications" + query, куки)
