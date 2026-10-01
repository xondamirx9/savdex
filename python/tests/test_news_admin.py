"""
Раздел «Новости» админки на Django — сквозь настоящую базу.

Главное здесь — два писателя одной таблицы по столбцам: текст пишет
форма, машинный перевод (*_i18n) — задача перевода. Проверяется, что:

- правка текста сбрасывает перевод именно этого поля, и добор перевода
  (savdex.translation_jobs) видит новость как недопереведённую;
- сохранение формы не затирает перевод, который задача записала,
  пока форма была открыта;
- обложка пересобирается и не копится на диске;
- «Опубликовать» / «Снять» одной кнопкой, дата публикации — ташкентская.

Нужен PostgreSQL (SAVDEX_PARITY_PG_URL); общая часть — в pg_admin.py.
"""

from __future__ import annotations

import io
from typing import Any

import pytest
from PIL import Image

from .pg_admin import (
    КОРЕНЬ,
    django,
    sql,
    журнал,
    нужна_база,
    свежая_база,
    сотрудник,
    файл,
)

pytestmark = нужна_база

LIST = "/py/admin/site/newspost/"
ADD = "/py/admin/site/newspost/add/"
PUBLIC = КОРЕНЬ / "storage/app/public"
PEREVOD = '{"en": "old", "uz": "old", "zh": "old", "tr": "old"}'


def _jpeg(size: tuple[int, int]) -> bytes:
    out = io.BytesIO()
    Image.new("RGB", size, (200, 120, 40)).save(out, "JPEG")

    return out.getvalue()


@pytest.fixture(scope="module")
def люди() -> dict[str, int]:
    свежая_база()

    return {role: сотрудник(role) for role in ("superadmin", "content_manager", "sales")}


@pytest.fixture(autouse=True)
def обложки():
    before = set(PUBLIC.glob("news/*"))

    yield

    for path in set(PUBLIC.glob("news/*")) - before:
        path.unlink()


def _форма(**поля: Any) -> dict[str, Any]:
    data = {
        "title": "Новые тарифы",
        "slug": "novye-tarify",
        "category": "Тарифы и оплата",
        "read_time": "",
        "excerpt": "Коротко о главном",
        "body": "Первый абзац.\n\nВторой абзац.",
        "published_at": "",
        "sort": "0",
    }
    data.update({k: v for k, v in поля.items() if v is not None})

    return data


def _row(slug: str) -> dict[str, Any]:
    [row] = sql(
        "select id, title_i18n::text, excerpt_i18n::text, body_i18n::text, image_path, "
        "author_id, is_published, published_at::text from news_posts where slug = %s",
        [slug],
    )
    keys = ("id", "title_i18n", "excerpt_i18n", "body_i18n", "image", "author", "published", "at")

    return dict(zip(keys, row, strict=True))


def _создать(люди: dict[str, int], slug: str, **поля: Any) -> dict[str, Any]:
    _, ответ = django(люди["content_manager"], ("post", ADD, _форма(slug=slug, **поля)))
    assert ответ["status"] == 302, ответ["body"][:3000]

    return _row(slug)


def _перевести(pk: int) -> None:
    """Как будто задача TranslateNewsPost отработала: все поля на всех языках."""
    sql(
        "update news_posts set title_i18n = %s, excerpt_i18n = %s, body_i18n = %s where id = %s",
        [PEREVOD, PEREVOD, PEREVOD, pk],
    )


def _недопереведённые() -> list[int]:
    """Порция добора перевода новостей — тот же запрос, что у translate."""
    from savdex.translation_jobs import CATCHUP

    _, query, limit = CATCHUP["news"]

    return [int(pk) for (pk,) in sql(query, [limit])]


def test_заведение_обложка_автор_время(люди):
    post = _создать(
        люди,
        "osennie-skidki",
        is_published="on",
        published_at="2026-10-01T09:00",
        cover_upload=файл("cover.jpg", _jpeg((3000, 1500))),
    )

    assert post["author"] == люди["content_manager"]
    # 09:00 в Ташкенте — 04:00 UTC
    assert post["at"] == "2026-10-01 04:00:00"
    assert post["image"].startswith("news/") and post["image"].endswith(".webp")
    with Image.open(PUBLIC / post["image"]) as cover:
        assert (cover.format, cover.size) == ("WEBP", (2000, 1000))

    запись = журнал("created")
    assert запись["section"] == "content"
    assert запись["subject_type"] == "App\\Models\\NewsPost"
    assert "title_i18n" not in запись["changes"]["after"]


@pytest.mark.parametrize(
    ("поля", "ошибка"),
    [
        ({"slug": "Новые тарифы"}, "Только латиница в нижнем регистре"),
        ({"excerpt": "я" * 501}, "Не больше 500 знаков."),
        ({"category": "Сплетни"}, "Выберите корректный вариант"),
        ({"cover_upload": файл("x.jpg", b"not a picture")}, "Файл не является изображением."),
    ],
)
def test_проверки_формы(люди, поля, ошибка):
    _, ответ = django(люди["content_manager"], ("post", ADD, _форма(**{"slug": "oshibka", **поля})))

    assert ответ["status"] == 200
    assert ошибка in ответ["body"]


def test_правка_текста_сбрасывает_перевод_этого_поля(люди):
    """
    Laravel переводил новость один раз: исправленный текст навсегда
    оставался на других языках со старым переводом.
    """
    post = _создать(люди, "perevod", is_published="on")
    _перевести(post["id"])
    assert post["id"] not in _недопереведённые()

    _, ответ = django(
        люди["content_manager"],
        (
            "post",
            f"{LIST}{post['id']}/change/",
            _форма(slug="perevod", is_published="on", body="Исправленный текст."),
        ),
    )

    assert ответ["status"] == 302, ответ["body"][:3000]
    after = _row("perevod")
    assert after["body_i18n"] is None, "перевод исправленного текста должен сброситься"
    assert after["title_i18n"] == PEREVOD and after["excerpt_i18n"] == PEREVOD
    # Добор перевода подберёт новость
    assert post["id"] in _недопереведённые()
    # В журнале — правка текста, а не перевода
    assert журнал("updated")["changes"]["after"] == {"body": "Исправленный текст."}


def test_сохранение_не_затирает_свежий_перевод(люди):
    """Задача перевода записала перевод, пока форма была открыта."""
    post = _создать(люди, "gonka", is_published="on")

    _, форма = django(люди["content_manager"], ("get", f"{LIST}{post['id']}/change/", None))
    assert форма["status"] == 200
    _перевести(post["id"])

    _, ответ = django(
        люди["content_manager"],
        ("post", f"{LIST}{post['id']}/change/", _форма(slug="gonka", is_published="on", sort="5")),
    )

    assert ответ["status"] == 302, ответ["body"][:3000]
    after = _row("gonka")
    assert (after["title_i18n"], after["excerpt_i18n"], after["body_i18n"]) == (PEREVOD,) * 3


def test_опубликовать_и_снять(люди):
    post = _создать(люди, "knopka")
    url = f"{LIST}{post['id']}/publish/"

    _, вопрос, опубликована = django(люди["content_manager"], ("get", url, None), ("post", url, {}))
    assert "Опубликовать новость «Новые тарифы»?" in вопрос["body"]
    assert опубликована["status"] == 302
    after = _row("knopka")
    assert after["published"] is True and after["at"] is not None
    # Видна на сайте: опубликована и дата не в будущем (NewsPost::published)
    assert sql(
        "select count(*) from news_posts where slug = 'knopka' and is_published "
        "and (published_at is null or published_at <= now())"
    ) == [(1,)]
    assert журнал("updated")["changes"]["after"]["is_published"] is True

    _, снята = django(люди["content_manager"], ("post", url, {}))
    assert снята["status"] == 302
    assert _row("knopka")["published"] is False


def test_список_статусы_и_права(люди):
    _создать(люди, "chernovik-1", title="Черновик новости")
    _создать(
        люди, "vyidet", title="Выйдет потом", is_published="on", published_at="2099-01-01T10:00"
    )

    _, черновики, расписание, чужой = (
        *django(
            люди["content_manager"],
            ("get", f"{LIST}?status=draft", None),
            ("get", f"{LIST}?status=scheduled", None),
        ),
        django(люди["sales"], ("get", LIST, None))[1],
    )

    assert "Черновик новости" in черновики["body"] and "Выйдет потом" not in черновики["body"]
    assert "Выйдет 01.01.2099" in расписание["body"]
    assert чужой["status"] == 403


def test_обложка_не_копится(люди):
    post = _создать(люди, "oblozhka", cover_upload=файл("a.jpg", _jpeg((1600, 900))))
    first = post["image"]

    _, замена = django(
        люди["content_manager"],
        (
            "post",
            f"{LIST}{post['id']}/change/",
            _форма(slug="oblozhka", cover_upload=файл("b.jpg", _jpeg((1600, 900)))),
        ),
    )
    assert замена["status"] == 302, замена["body"][:3000]
    second = _row("oblozhka")["image"]
    assert second != first and (PUBLIC / second).exists()
    assert not (PUBLIC / first).exists(), "прежняя обложка осталась на диске"

    _, удалена = django(
        люди["superadmin"], ("post", f"{LIST}{post['id']}/delete/", {"post": "yes"})
    )
    assert удалена["status"] == 302
    assert not (PUBLIC / second).exists()
