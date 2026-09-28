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
                "now() - make_interval(hours => %s + 1, mins => 30), now())",
                [owner, зритель, объявление, i + j],
            )

    # Раскрытия — часами раньше: «N секунд назад» разошлось бы между сторонами
    sql(
        "update contact_unlocks set "
        "created_at = now() - make_interval(hours => id::int, mins => 30)"
    )

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
    sql("update reviews set created_at = now() - make_interval(hours => id::int, mins => 30)")
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
    sql(
        "update contact_unlocks set "
        "created_at = now() - make_interval(hours => id::int, mins => 30)"
    )


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
                "%s, %s, %s, %s, now() - make_interval(hours => %s, mins => 30), now())",
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


# ── Избранное ───────────────────────────────────────────────────────


@pytest.mark.parametrize("path", ["/favorites", "/uz/favorites"])
def test_избранное(сайт, path):
    куки = владелец(сайт)
    [(uid,)] = sql("select id from users where email = 'owner@savdex.uz'")

    if not sql("select 1 from favorites where user_id = %s", [uid]):
        php(
            "$seller = App\\Models\\Company::factory()->create();"
            "$gone = App\\Models\\Company::factory()->create();"
            "$ids = [];"
            "foreach (['active', 'expired', 'archived', 'draft', 'moderation'] as $s) {"
            " $ids[] = App\\Models\\Listing::factory()->create(['company_id' => $seller->id,"
            " 'status' => $s, 'published_at' => '2026-09-20 10:00:00'])->id; }"
            "$trashed = App\\Models\\Listing::factory()->create(['company_id' => $seller->id]);"
            "$ids[] = $trashed->id; $trashed->delete();"
            "$ids[] = App\\Models\\Listing::factory()->create(['company_id' => $gone->id,"
            " 'published_at' => '2026-09-21 10:00:00'])->id; $gone->delete();"
            "foreach ($ids as $id) { App\\Models\\Favorite::create(['user_id' => "
            + str(uid)
            + ", 'listing_id' => $id]); }"
            "echo 'ok';",
            {"MACHINE_TRANSLATION_ENABLED": "false"},
        )

    д, _ = сверить(сайт, path, куки)
    items = страница(д["body"])["props"]["items"]

    assert len(items) == 4 and [i["active"] for i in items].count(False) == 2


# ── Мои объявления ──────────────────────────────────────────────────


def _объявления() -> None:
    """Объявления всех вкладок, два значка продвижения, замечание модератора."""
    if sql("select 1 from listings where status = 'needs_changes'"):
        return

    subprocess.run(
        ["php", "artisan", "db:seed", "--class=PromotionTypeSeeder", "--force"],
        cwd=КОРЕНЬ,
        env=ОКРУЖЕНИЕ,
        check=True,
        capture_output=True,
    )
    php(
        "$c = App\\Models\\Company::where('slug', 'owner')->first();"
        "foreach (['needs_changes', 'expired', 'rejected', 'archived'] as $s) {"
        " App\\Models\\Listing::factory()->create(['company_id' => $c->id, 'status' => $s,"
        " 'moderation_note' => $s === 'needs_changes' ? 'Добавьте фото' : null]); }"
        "$l = $c->listings()->where('status', 'active')->orderBy('id')->first();"
        "foreach (['urgent', 'highlight'] as $code) { App\\Models\\Promotion::create(["
        "'listing_id' => $l->id, 'company_id' => $c->id, 'units_spent' => 1,"
        "'promotion_type_id' => App\\Models\\PromotionType::where('code', $code)->value('id'),"
        "'status' => 'active', 'starts_at' => now(), 'ends_at' => now()->addDays(3)]); }"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )
    # Массовое действие — одна секунда у всех: порядок решает id
    sql("update listings set updated_at = '2026-09-25 12:00:00'")


@pytest.mark.parametrize(
    "query",
    [
        "",
        "?status=draft",
        "?status=needs_changes",
        "?status=expired",
        "?status=archived",
        "?status=",
    ],
)
def test_мои_объявления(сайт, query):
    _объявления()
    сверить(сайт, "/cabinet/listings" + query, владелец(сайт))


def test_мои_объявления_по_узбекски(сайт):
    _объявления()
    сверить(сайт, "/uz/cabinet/listings", владелец(сайт))


def test_мои_объявления_без_компании(сайт):
    пользователь("nocompany7@savdex.uz")
    сверить(сайт, "/cabinet/listings", войти(сайт, "nocompany7@savdex.uz"))


# ── Чаты ────────────────────────────────────────────────────────────


def _чаты() -> None:
    """Разговоры: обе стороны, собеседник в корзине, IT-задача, пустой, прочитанное."""
    if sql("select count(*) from message_threads")[0][0] > 1:
        return

    php(
        "$c = App\\Models\\Company::where('slug', 'owner')->first();"
        "$l = $c->listings()->orderBy('id')->first();"
        "$task = App\\Models\\ItTask::factory()->create();"
        "foreach (range(0, 4) as $i) { $o = App\\Models\\Company::factory()->create();"
        " $t = App\\Models\\MessageThread::create(["
        " 'buyer_company_id' => $i % 2 ? $c->id : $o->id,"
        " 'seller_company_id' => $i % 2 ? $o->id : $c->id,"
        " 'listing_id' => $i === 0 ? $l->id : null, 'it_task_id' => $i === 1 ? $task->id : null]);"
        " if ($i < 4) { foreach (range(1, 3) as $k) { App\\Models\\Message::create(["
        " 'thread_id' => $t->id, 'company_id' => $k === 3 && $i === 2 ? $c->id : $o->id,"
        " 'body' => str_repeat('Сообщение '.$k.' ', $k * 5)]); } }"
        " if ($i === 3) { $o->delete(); } }"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )
    sql("update messages set created_at = now() - make_interval(hours => 50 - id::int, mins => 30)")
    sql(
        "update message_threads t set last_message_at = (select max(created_at) from messages m "
        "where m.thread_id = t.id)"
    )
    # Прочитано до второго сообщения — у одной стороны
    sql(
        "update message_threads t set seller_read_at = (select min(created_at) from messages m "
        "where m.thread_id = t.id) + interval '1 minute' where t.id = (select min(id) from "
        "message_threads where seller_company_id = (select id from companies where slug = 'owner'))"
    )


@pytest.mark.parametrize("path", ["/cabinet/chats", "/en/cabinet/chats"])
def test_чаты(сайт, path):
    _чаты()
    сверить(сайт, path, владелец(сайт))


def test_чаты_без_компании(сайт):
    пользователь("nocompany8@savdex.uz")
    сверить(сайт, "/cabinet/chats", войти(сайт, "nocompany8@savdex.uz"))


# ── Продвижение ─────────────────────────────────────────────────────


@pytest.mark.parametrize("path", ["/cabinet/promo", "/uz/cabinet/promo"])
def test_продвижение(сайт, path):
    _объявления()
    # Эффект: прирост показов; у второго «до» — ноль (эффекта нет); одна секунда
    sql(
        "update promotions set impressions_before = case when mod(id, 2) = 0 then 40 else 0 end, "
        "impressions_after = 57, created_at = '2026-09-26 09:00:00'"
    )
    сверить(сайт, path, владелец(сайт))


def test_продвижение_без_компании(сайт):
    пользователь("nocompany9@savdex.uz")
    сверить(сайт, "/cabinet/promo", войти(сайт, "nocompany9@savdex.uz"))


# ── Моё резюме ──────────────────────────────────────────────────────


def test_резюме_пустое(сайт):
    пользователь("seeker0@savdex.uz", phone="+998900000001")
    сверить(сайт, "/cabinet/resume", войти(сайт, "seeker0@savdex.uz"))


@pytest.mark.parametrize("path", ["/cabinet/resume", "/uz/cabinet/resume", "/zh/cabinet/resume"])
def test_резюме(сайт, path):
    email = "seeker@savdex.uz"

    if not sql("select 1 from users where email = %s", [email]):
        uid = пользователь(email)
        php(
            "$r = new App\\Models\\Resume();"
            "$r->forceFill(['user_id' => "
            + str(uid)
            + ", 'slug' => 'logist', 'title' => 'Логист', 'field' => 'logistics',"
            "'salary' => 1200, 'currency' => 'USD', 'employment' => ['full', 'project'],"
            "'skills' => ['1С', 'Excel'], 'jobs' => [['company' => 'Стройбаза',"
            " 'position' => 'Логист', 'from' => '2020-01', 'to' => null]],"
            "'experience_months' => 45, 'photo_path' => 'resumes/p.webp',"
            "'moderation_note' => 'Уточните зарплату', 'status' => 'draft'])->save();"
            "echo 'ok';",
            {"MACHINE_TRANSLATION_ENABLED": "false"},
        )

    сверить(сайт, path, войти(сайт, email))


# ── Профиль компании ────────────────────────────────────────────────


def _документы() -> None:
    """Документы разных видов, файл на диске у одного; сотрудник; контакты."""
    if sql("select 1 from company_documents limit 1"):
        return

    файл = КОРЕНЬ / "storage/app/private/docs/reg.pdf"
    файл.parent.mkdir(parents=True, exist_ok=True)
    файл.write_bytes(b"%PDF-1.4 test")
    php(
        "$c = App\\Models\\Company::where('slug', 'owner')->first();"
        "foreach ([['registration', 'approved', 'docs/reg.pdf', 2500000],"
        " ['license', 'pending', 'docs/lic.pdf', 20480],"
        " ['price_list', 'pending', 'docs/p.xlsx', null]]"
        " as [$type, $status, $path, $size]) { $d = new App\\Models\\CompanyDocument();"
        " $d->forceFill(['company_id' => $c->id, 'type' => $type, 'title' => 'Док '.$type,"
        " 'file_path' => $path, 'file_size' => $size, 'is_public' => $type !== 'license',"
        " 'moderation_status' => $status,"
        " 'valid_until' => $type === 'license' ? '2027-01-31' : null,"
        " 'created_at' => '2026-09-20 10:00:00'])->save(); }"
        "$c->contacts()->create(['type' => 'phone', 'value' => '+998901234567',"
        " 'label' => 'Отдел продаж',"
        " 'contact_person' => 'Азиз', 'is_public' => true, 'is_primary' => true]);"
        "$c->contacts()->create(['type' => 'email', 'value' => 'sales@owner.uz',"
        " 'is_public' => false]);"
        "App\\Models\\User::factory()->create(['company_id' => $c->id, 'company_role' => 'staff',"
        " 'email_verified_at' => null]);"
        "echo 'ok';"
    )


@pytest.mark.parametrize("path", ["/cabinet/company", "/uz/cabinet/company"])
def test_профиль_компании(сайт, path):
    _документы()
    sql(
        "update users set company_role = 'owner', phone_verified_at = '2026-09-01 10:00:00' "
        "where email = 'owner@savdex.uz'"
    )
    сверить(сайт, path, владелец(сайт))


def test_профиль_без_компании(сайт):
    пользователь("nocompany10@savdex.uz")
    сверить(сайт, "/cabinet/company", войти(сайт, "nocompany10@savdex.uz"))


# ── Мои IT-задачи ───────────────────────────────────────────────────


def _задачи() -> int:
    """IT-задачи владельца: бюджеты трёх видов, исполнитель, отклики, файлы."""
    [(owner,)] = sql("select id from companies where slug = 'owner'")

    if not sql("select 1 from it_tasks where company_id = %s", [owner]):
        php(
            "$c = App\\Models\\Company::where('slug', 'owner')->first();"
            "$dev = App\\Models\\Company::factory()->create(['name' => 'Tashkent Soft']);"
            "foreach ([['fixed', 1500000, null, 'UZS'], ['range', 500, 900, 'USD'],"
            " ['negotiable', null, null, 'UZS']] as $i => [$type, $from, $to, $cur]) {"
            " $t = App\\Models\\ItTask::factory()->create(['company_id' => $c->id,"
            " 'budget_type' => $type, 'budget_from' => $from, 'budget_to' => $to,"
            " 'currency' => $cur, 'status' => ['active', 'completed', 'closed'][$i],"
            " 'contractor_company_id' => $i === 1 ? $dev->id : null,"
            " 'deadline_at' => $i === 0 ? '2026-12-01' : null, 'stack' => ['Laravel', 'React'],"
            " 'created_at' => '2026-09-20 10:00:00'])->id;"
            " if ($i === 0) {"
            " foreach ([$dev, App\\Models\\Company::factory()->create()] as $k => $b)"
            " { App\\Models\\MessageThread::create(['buyer_company_id' => $b->id,"
            " 'seller_company_id' => $c->id, 'it_task_id' => $t]);"
            " if ($k === 1) { $b->delete(); } }"
            " foreach ([2048, 3500000] as $size) { $f = new App\\Models\\ItTaskFile();"
            " $f->forceFill(['it_task_id' => $t, 'title' => 'ТЗ '.$size,"
            " 'file_path' => 'it/'.$size,"
            " 'file_size' => $size, 'mime' => 'application/pdf'])->save(); } } }"
            "echo 'ok';",
            {"MACHINE_TRANSLATION_ENABLED": "false"},
        )

    [(first,)] = sql(
        "select min(id) from it_tasks where company_id = %s and budget_type = 'fixed'", [owner]
    )

    return int(first)


@pytest.mark.parametrize("path", ["/cabinet/it-tasks", "/uz/cabinet/it-tasks"])
def test_мои_задачи(сайт, path):
    _задачи()
    сверить(сайт, path, владелец(сайт))


def test_задача_форма(сайт):
    task = _задачи()
    куки = владелец(сайт)

    сверить(сайт, "/cabinet/it-tasks/create", куки)
    сверить(сайт, f"/cabinet/it-tasks/{task}/edit", куки)

    php("App\\Models\\ItTask::factory()->create(); echo 'ok';")
    [(чужая,)] = sql(
        "select min(id) from it_tasks where company_id != (select id from companies "
        "where slug = 'owner')"
    )
    д, _ = сверить(сайт, f"/cabinet/it-tasks/{чужая}/edit", куки)
    assert д["status"] == 404


def test_задачи_без_компании(сайт):
    пользователь("nocompany11@savdex.uz")
    куки = войти(сайт, "nocompany11@savdex.uz")
    сверить(сайт, "/cabinet/it-tasks", куки)

    # Без компании форма уводит в профиль с предупреждением в сессии
    стороны = по_сторонам(сайт, "/cabinet/it-tasks/create", lambda: None, cookies=куки)
    итог = одинаково(стороны)

    assert стороны["django"][0]["headers"]["location"].endswith("/cabinet/company")
    assert '"warning":' in итог["payload"]


# ── Мини-сайт ───────────────────────────────────────────────────────


def test_мини_сайт_без_сайта(сайт):
    sql(
        "delete from company_sites where company_id = (select id from companies "
        "where slug = 'owner')"
    )
    сверить(сайт, "/cabinet/site", владелец(сайт))


def test_мини_сайт(сайт):
    фон = КОРЕНЬ / "storage/app/public/sites/1/hero.webp"
    фон.parent.mkdir(parents=True, exist_ok=True)
    фон.write_bytes(b"RIFF")
    php(
        "$c = App\\Models\\Company::where('slug', 'owner')->first();"
        "App\\Models\\CompanySite::query()->where('company_id', $c->id)->delete();"
        "$s = new App\\Models\\CompanySite();"
        "$s->forceFill(['company_id' => $c->id, 'subdomain' => 'owner-shop',"
        " 'status' => 'published', 'published_at' => '2026-09-21 14:30:00',"
        " 'theme' => ['template' => 'bold', 'primary' => '#AABBCC', 'mode' => 'neon',"
        "  'hero_image' => 'sites/1/hero.webp', 'extra' => 'x'],"
        " 'published_theme' => ['template' => 'classic']])->save();"
        "App\\Models\\CompanySiteProduct::query()->where('company_id', $c->id)->delete();"
        "foreach ([[2, 'Цемент', 45000], [1, 'Арматура', null], [1, 'Щебень', 120]]"
        " as [$sort, $t, $p])"
        " { $x = new App\\Models\\CompanySiteProduct(); $x->forceFill(['company_id' => $c->id,"
        " 'title' => $t, 'price' => $p, 'currency' => 'UZS', 'sort' => $sort,"
        " 'image_path' => $t === 'Цемент' ? 'sites/1/hero.webp' : null])->save(); }"
        "echo 'ok';"
    )
    куки = владелец(сайт)

    for path in ("/cabinet/site", "/uz/cabinet/site"):
        сверить(сайт, path, куки)


def test_мини_сайт_без_компании(сайт):
    пользователь("nocompany12@savdex.uz")
    д, _ = сверить(сайт, "/cabinet/site", войти(сайт, "nocompany12@savdex.uz"))
    assert д["status"] == 302


# ── Разговор ────────────────────────────────────────────────────────


def test_разговор_отмечает_прочитанное(сайт):
    _чаты()
    [(owner,)] = sql("select id from companies where slug = 'owner'")
    threads = sql(
        "select id, buyer_company_id = %s from message_threads where %s in "
        "(buyer_company_id, seller_company_id) and exists (select 1 from messages m "
        "where m.thread_id = message_threads.id) order by id",
        [owner, owner],
    )
    куки = владелец(сайт)

    for thread, is_buyer in threads[:3]:
        column, other = (
            ("buyer_read_at", "seller_read_at") if is_buyer else ("seller_read_at", "buyer_read_at")
        )
        [(before_other,)] = sql(f"select {other} from message_threads where id = %s", [thread])
        снимки = []

        def сбросить(thread: int = thread, column: str = column) -> None:
            sql(f"update message_threads set {column} = null where id = %s", [thread])

        def снять(
            _: object,
            thread: int = thread,
            column: str = column,
            other: str = other,
            before: object = before_other,
            снимки: list[object] = снимки,
        ) -> None:
            снимки.append(
                sql(
                    f"select {column} is not null and {column} > now() - interval '1 minute', "
                    f"{other} is not distinct from %s from message_threads where id = %s",
                    [before, thread],
                )[0]
            )

        сверить(сайт, f"/cabinet/chats/{thread}", куки, перед=сбросить, после=снять)

        # Отмечена своя сторона, чужая не тронута — у обеих
        assert снимки == [(True, True), (True, True)], снимки


def test_чужой_разговор_404(сайт):
    _чаты()
    [(owner,)] = sql("select id from companies where slug = 'owner'")
    php(
        "App\\Models\\MessageThread::create(['buyer_company_id' => App\\Models\\Company::factory()"
        "->create()->id, 'seller_company_id' => App\\Models\\Company::factory()->create()->id]);"
        "echo 'ok';"
    )
    [(чужой,)] = sql(
        "select max(id) from message_threads where %s not in (buyer_company_id, seller_company_id)",
        [owner],
    )
    куки = владелец(сайт)

    for path in (f"/cabinet/chats/{чужой}", "/cabinet/chats/999999"):
        д, _ = сверить(сайт, path, куки)
        assert д["status"] == 404


# ── Мастер объявления ───────────────────────────────────────────────


def _черновик() -> int:
    """Черновик владельца в подразделе с полями, характеристиками и фото."""
    if not sql("select 1 from categories where parent_id is not null limit 1"):
        subprocess.run(
            ["php", "artisan", "db:seed", "--class=CategorySeeder", "--force"],
            cwd=КОРЕНЬ,
            env=ОКРУЖЕНИЕ,
            check=True,
            capture_output=True,
        )

    found = sql("select id from listings where slug = 'wizard-draft'")

    if found:
        return int(found[0][0])

    php(
        "$c = App\\Models\\Company::where('slug', 'owner')->first();"
        "$child = App\\Models\\Category::whereNotNull('parent_id')->orderBy('id')->first();"
        "$child->fields()->updateOrCreate(['key' => 'mark'], ['label' => 'Марка',"
        " 'type' => 'select', 'options' => ['М400', 'М500'], 'sort' => 1]);"
        "$l = App\\Models\\Listing::factory()->draft()->create(['company_id' => $c->id,"
        " 'slug' => 'wizard-draft', 'category_id' => $child->id,"
        " 'title' => 'Цемент М400 навалом 50 кг', 'tags' => ['цемент'], 'wizard_step' => 3]);"
        "foreach ([['weight', '50 кг'], ['mark', 'М400'], ['spec_weight', '50 kg'],"
        " ['spec_color', 'grey']] as [$k, $v])"
        " { $l->attributes()->create(['key' => $k, 'value' => $v]); }"
        "foreach ([1, 0] as $i => $sort) { $l->images()->create(['path' => 'l/w'.$i.'.webp',"
        " 'thumb_path' => $i ? null : 'l/wt'.$i.'.webp', 'sort' => $sort]); }"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )

    return int(sql("select id from listings where slug = 'wizard-draft'")[0][0])


@pytest.mark.parametrize("prefix", ["", "/uz"])
def test_мастер_объявления(сайт, prefix):
    listing = _черновик()
    д, _ = сверить(сайт, f"{prefix}/cabinet/listings/{listing}/edit", владелец(сайт))
    props = страница(д["body"])["props"]

    # Блок «Информация о товаре» (ProductSpecs): поля у каждого подраздела,
    # детали в теги не идут. Пока ProductSpecs у Laravel нет — блока нет
    if not (КОРЕНЬ / "lang/ru/specs.php").exists():
        assert not any("specs" in c for p in props["categories"] for c in p["children"])
        return

    assert all("specs" in c for p in props["categories"] for c in p["children"])
    assert any(c["specs"] for p in props["categories"] for c in p["children"])
    assert "50 kg" not in props["tagOptions"]


def test_мастер_чужое_и_неподтверждённая_почта(сайт):
    listing = _черновик()
    чужое = int(
        php("echo App\\Models\\Listing::factory()->draft()->create()->id;").splitlines()[-1]
    )
    д, _ = сверить(сайт, f"/cabinet/listings/{чужое}/edit", владелец(сайт))
    assert д["status"] == 404

    пользователь("unverified@savdex.uz")
    sql(
        "update users set email_verified_at = null, company_id = (select id from companies "
        "where slug = 'owner') where email = 'unverified@savdex.uz'"
    )
    куки = войти(сайт, "unverified@savdex.uz")
    стороны = по_сторонам(сайт, f"/cabinet/listings/{listing}/edit", lambda: None, cookies=куки)
    итог = одинаково(стороны)

    assert стороны["django"][0]["headers"]["location"].endswith("/verify-email")
    assert '"intended":' in итог["payload"]
