"""
Этап 4, шаг 2: лента «IT-услуги» на Django неотличима от Laravel.

Открытые и выполненные задачи, поиск по search_text, направления и
виды, город, «проверенные», «с бюджетом», постраничный вывод; карточка
с исполнителем и адресом результата; для вошедшего — исполнитель ли он.

Нужны PHP и PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в web_site.py.
"""

from __future__ import annotations

import subprocess
from collections.abc import Iterator

import pytest

from .pg_admin import КОРЕНЬ, ОКРУЖЕНИЕ, php, sql, нужна_база, свежая_база
from .web_site import laravel, войти, из_django, из_laravel, пользователь, сверить, страница

pytestmark = нужна_база


@pytest.fixture(scope="module")
def сайт() -> Iterator[str]:
    свежая_база()
    subprocess.run(
        ["php", "artisan", "db:seed", "--class=GeoSeeder", "--force"],
        cwd=КОРЕНЬ,
        env=ОКРУЖЕНИЕ,
        check=True,
        capture_output=True,
    )
    # 26 открытых (две страницы), 3 выполненных, закрытая и задача
    # заблокированной компании
    php(
        "$uz = App\\Models\\Country::where('code', 'uz')->value('id');"
        "$cities = App\\Models\\City::where('country_id', $uz)->orderBy('id')"
        "->limit(2)->pluck('id');"
        "$types = ['web', 'mobile', 'logistics', 'hr', 'accounting', 'design'];"
        "$budgets = ['fixed', 'range', 'negotiable'];"
        "$companies = collect(range(0, 3))->map(fn ($i) => "
        "App\\Models\\Company::factory()->create(["
        "'country_id' => $uz, 'city_id' => $i < 3 ? $cities[$i % 2] : null,"
        "'verification_level' => $i, 'is_it_provider' => $i === 1]));"
        "foreach (range(1, 26) as $i) { App\\Models\\ItTask::factory()->create(["
        "'company_id' => $companies[$i % 4]->id, 'service_type' => $types[$i % 6],"
        "'budget_type' => $budgets[$i % 3], 'budget_to' => $i % 3 === 1 ? 50000000 : null,"
        "'budget_from' => $i % 3 === 2 ? null : 1500000.5,"
        "'deadline_at' => $i % 5 ? '2026-10-'.(10 + $i) : null,"
        "'title' => $i % 7 ? 'Сайт для склада '.$i : 'Sayt yaratish '.$i,"
        "'published_at' => Carbon\\Carbon::parse('2026-09-01 12:00:00')->subHours($i % 9)]); }"
        "foreach (range(1, 3) as $i) { App\\Models\\ItTask::factory()->create(["
        "'company_id' => $companies[0]->id, 'status' => 'completed',"
        "'completed_at' => Carbon\\Carbon::parse('2026-09-0'.$i.' 23:30:00'),"
        "'contractor_company_id' => $i === 3 ? null : $companies[1]->id,"
        "'result_url' => $i === 1 ? 'https://www.Example.uz:8443/case?x=1' : null,"
        "'result_summary' => 'Сделали за месяц']); }"
        "App\\Models\\ItTask::factory()->closed()->create(['company_id' => $companies[0]->id]);"
        "$blocked = App\\Models\\Company::factory()->create(['status' => 'blocked']);"
        "App\\Models\\ItTask::factory()->create(['company_id' => $blocked->id]);"
        "echo 'ok';",
        {"MACHINE_TRANSLATION_ENABLED": "false"},
    )

    with laravel() as root:
        yield root


@pytest.mark.parametrize(
    "path",
    [
        "/it-services",
        "/it-services?page=2",
        "/it-services?page=3",
        "/en/it-services",
        "/uz/it-services?page=2",
        "/it-services?done=1",
        "/it-services?done=yes&page=1",
        "/it-services?done=0",
        "/it-services?q=%D1%81%D0%BA%D0%BB%D0%B0%D0%B4",
        "/it-services?q=sayt",
        "/it-services?q=%20%20",
        "/it-services?type=it",
        "/it-services?type=hr_services",
        "/it-services?type=accounting&with_budget=on",
        "/it-services?type=nonsense",
        "/it-services?verified=true",
        "/it-services?with_budget=1&verified=1&page=2",
        "/it-services?city=abc",
    ],
)
def test_лента(сайт, path):
    сверить(сайт, path)


def test_фильтр_по_городу(сайт):
    д, _ = сверить(сайт, "/it-services")
    города = страница(д["body"])["props"]["cities"]

    assert города
    сверить(сайт, f"/tr/it-services?city={города[0]['id']}")


def test_выполненные_с_исполнителем(сайт):
    д, _ = сверить(сайт, "/it-services?done=1")
    задачи = страница(д["body"])["props"]["tasks"]["data"]

    assert [t["result_host"] for t in задачи].count("Example.uz") == 1
    assert sum(t["contractor"] is not None for t in задачи) == 2


def test_вошедший_исполнитель(сайт):
    пользователь("it@savdex.uz")
    php(
        "$c = App\\Models\\Company::where('is_it_provider', true)->first();"
        "App\\Models\\User::where('email', 'it@savdex.uz')->update(['company_id' => $c->id]);"
        "echo 'ok';"
    )
    куки = войти(сайт, "it@savdex.uz")
    д, _ = сверить(сайт, "/it-services", куки)

    assert страница(д["body"])["props"]["viewer"] == {"guest": False, "provider": True}


def адрес(условие: str) -> str:
    return str(sql(f"select slug from it_tasks where {условие} order by id limit 1")[0][0])


def test_страница_задачи(сайт):
    открытая = адрес("status = 'active'")
    sql(
        "insert into it_task_files (it_task_id, title, file_path, file_size, mime, created_at, "
        "updated_at) select id, t, p, s, 'application/pdf', now(), now() from it_tasks, "
        "(values ('ТЗ.PDF', 'it/a.pdf', 1536000), ('схема', 'it/b.Docx', 300), "
        "('архив.tar.gz', 'it/c', 0)) as f(t, p, s) where slug = %s",
        [открытая],
    )

    for prefix in ("", "/en", "/uz"):
        сверить(сайт, f"{prefix}/it-services/{открытая}", перед=обнулить)

    # Выполненная с результатом; задача заблокированной компании
    выполненная = адрес("status = 'completed'")
    чужая = адрес("company_id = (select max(id) from companies)")
    сверить(сайт, f"/zh/it-services/{выполненная}", перед=обнулить)
    сверить(сайт, f"/it-services/{чужая}", перед=обнулить)


def обнулить() -> None:
    """Счётчик просмотров — с нуля перед каждой стороной сверки."""
    sql("update it_tasks set views_count = 0")


def test_закрытая_видна_только_заказчику(сайт):
    закрытая = адрес("status = 'closed'")
    д, _ = сверить(сайт, f"/it-services/{закрытая}")
    assert д["status"] == 404

    пользователь("owner@savdex.uz")
    sql(
        "update users set company_id = (select company_id from it_tasks where slug = %s) "
        "where email = 'owner@savdex.uz'",
        [закрытая],
    )
    куки = войти(сайт, "owner@savdex.uz")
    д, _ = сверить(сайт, f"/it-services/{закрытая}", куки, перед=обнулить)
    assert страница(д["body"])["props"]["respond"]["owner"] is True
    # Свой просмотр не считается
    assert sql("select views_count from it_tasks where slug = %s", [закрытая])[0][0] == 0


def test_нет_задачи(сайт):
    д, _ = сверить(сайт, "/it-services/nothing")
    assert д["status"] == 404


def test_просмотр_администратора_в_журнале(сайт):
    пользователь("boss@savdex.uz", is_admin=True, admin_role="superadmin")
    куки = войти(сайт, "boss@savdex.uz")
    slug = адрес("status = 'active'")
    sql("delete from admin_actions")

    из_laravel(сайт, f"/it-services/{slug}", куки)
    из_django(сайт, f"/it-services/{slug}", куки)

    л, д = sql(
        "select user_name, action, section, subject_type, subject_id, subject_label, "
        "changes::jsonb from admin_actions order by id"
    )
    assert л[:6] == д[:6] and л[2] == "ittasks"
    assert д[6]["after"]["views_count"] == л[6]["after"]["views_count"] + 1
