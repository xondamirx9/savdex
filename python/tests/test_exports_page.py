"""
Шаг 68: «Выгрузка в Excel» в админке Django (savdex/system/exports.py,
savdex/system/exports_view.py) вместо страницы Filament ExcelExports.

Без базы: сотрудник подменён, журнал и фоновый запуск перехвачены,
выгрузки лежат во временной папке. Сквозная проверка на PostgreSQL
(кнопка → фоновый процесс → две сошедшиеся книги → скачивание) —
в конце файла, ей нужна SAVDEX_PARITY_PG_URL.
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from typing import Any

import pytest
from django.test import Client

from savdex import access, audit, bridge
from savdex.system import exports

APP_KEY = "base64:" + base64.b64encode(b"k" * 32).decode()
КНИГИ = ("savdex-companies-2026-09-30-1500.xlsx", "savdex-listings-2026-09-30-1500.xlsx")


def сотрудник(uid: int, role: str, **поправки: Any) -> access.Admin:
    return access.Admin(
        id=uid,
        name=f"Сотрудник {uid}",
        email=f"u{uid}@savdex.uz",
        is_admin=True,
        role=role,
        status="active",
        **поправки,
    )


@pytest.fixture
def среда(monkeypatch, settings, tmp_path):
    monkeypatch.setenv("APP_KEY", APP_KEY)
    monkeypatch.setenv("SAVDEX_EXPORTS_DIR", str(tmp_path))
    settings.SECRET_KEY = "проверочный-ключ-" + "x" * 40
    settings.SECRET_KEY_IS_REAL = True
    люди = {
        1: сотрудник(1, access.SUPERADMIN),
        2: сотрудник(2, "content_manager"),
        # Выдано лично только смотреть: скачивать нельзя
        3: сотрудник(3, "content_manager", permissions={"grant": ["backups.view"]}),
    }
    monkeypatch.setattr(bridge, "load_admin", lambda _conn, uid: люди.get(uid))
    from savdex.dashboard import widgets
    from savdex.web import shared

    # Базы здесь нет: виджеты главной и логотип читают её
    monkeypatch.setattr(widgets, "for_request", lambda request: [])
    monkeypatch.setattr(shared, "settings_values", lambda: {})
    журнал: list[dict[str, Any]] = []
    monkeypatch.setattr(audit, "record", lambda _conn, **row: журнал.append(row))
    запуски: list[str] = []
    monkeypatch.setattr(exports, "start", запуски.append)

    return {"dir": tmp_path, "журнал": журнал, "запуски": запуски}


def браузер(uid: int) -> Client:
    client = Client()
    client.cookies[bridge.COOKIE] = bridge.session_cookie(uid)

    return client


def выгрузка(folder: Path, run_id: str, books: tuple[str, ...] = (), **run: Any) -> None:
    (folder / run_id).mkdir()
    (folder / run_id / "run.json").write_text(json.dumps({"id": run_id, **run}))

    for book in books:
        (folder / run_id / book).write_bytes(b"PK-" + book.encode())


def test_без_права_403_и_ссылки_нет(среда):
    client = браузер(2)

    assert client.get("/py/admin/exports/").status_code == 403
    assert client.post("/py/admin/exports/").status_code == 403
    assert "Выгрузка в Excel" not in client.get("/py/admin/").content.decode()


def test_пусто_и_кнопка(среда):
    page = браузер(1).get("/py/admin/exports/")
    body = page.content.decode()

    assert page.status_code == 200
    assert "Выгрузок пока нет" in body
    assert 'value="Выгрузить сейчас"' in body and "disabled" not in body
    assert 'http-equiv="refresh"' not in body
    # Ссылка в шапке ведёт сюда, а не на Filament
    assert 'href="/py/admin/exports/"' in body and "/admin/excel-exports" not in body


def test_запуск_журнал_и_вторая_не_запускается(среда):
    client = браузер(1)

    ответ = client.post("/py/admin/exports/")

    assert ответ.status_code == 302 and ответ["Location"] == "/py/admin/exports/"
    [run_id] = среда["запуски"]
    assert exports.ID.fullmatch(run_id)
    run = exports.find(run_id)
    assert run is not None
    assert run["status"] == exports.QUEUED and run["requested_by"] == "Сотрудник 1"
    assert run["requested_by_id"] == 1
    assert среда["журнал"] == [
        {
            "action": "exported",
            "section": "backups",
            "actor": bridge.load_admin(None, 1),  # type: ignore[arg-type]
            "note": f"Выгрузка базы в Excel: {run_id}",
            "ip": "127.0.0.1",
        }
    ]

    page = client.get("/py/admin/exports/").content.decode()
    assert "в очереди" in page and 'http-equiv="refresh" content="5"' in page
    assert "disabled" in page

    client.post("/py/admin/exports/")

    assert len(среда["запуски"]) == 1 and len(среда["журнал"]) == 1
    assert len(exports.all_runs()) == 1


def test_список_и_скачивание(среда):
    folder = среда["dir"]
    выгрузка(
        folder,
        "2026-09-30-100000-aaaa",
        КНИГИ,
        status="done",
        engine="python",
        files=list(КНИГИ),
        python={"status": "self", "self_check": True},
        requested_by="Анна",
        queued_at="2026-09-30T10:00:00+00:00",
    )
    # Выгрузка до переезда: книги PHP, сверка с Python
    выгрузка(
        folder,
        "2026-09-01-100000-bbbb",
        ("savdex-companies-2026-09-01-1500.xlsx",),
        status="done",
        php={"files": ["savdex-companies-2026-09-01-1500.xlsx"]},
        python={"status": "differs", "differences": 3, "problems": ["Компании!B2"]},
        queued_at="2026-09-01T10:00:00+00:00",
    )
    client = браузер(1)

    body = client.get("/py/admin/exports/").content.decode()

    # Время — по Ташкенту
    assert "30.09.2026 15:00" in body and "Анна" in body
    assert "сошлась с базой" in body and "книги Python-версии" in body
    assert "расходится: 3" in body and "книги PHP-версии" in body and "Компании!B2" in body
    assert body.index("2026-09-30-100000-aaaa") < body.index("2026-09-01-100000-bbbb")
    ссылка = f"/py/admin/exports/2026-09-30-100000-aaaa/{КНИГИ[0]}"
    assert ссылка in body

    файл = client.get(ссылка)

    assert файл.status_code == 200
    assert b"".join(файл.streaming_content) == b"PK-" + КНИГИ[0].encode()  # type: ignore[attr-defined]
    assert f'filename="{КНИГИ[0]}"' in файл["Content-Disposition"]
    assert среда["журнал"][-1]["action"] == "downloaded"
    assert среда["журнал"][-1]["note"] == f"Скачан файл выгрузки 2026-09-30-100000-aaaa/{КНИГИ[0]}"


@pytest.mark.parametrize(
    "path",
    [
        "2026-09-30-100000-aaaa/run.json",
        "2026-09-30-100000-aaaa/savdex-users-2026.xlsx",
        "2026-09-30-100000-zzzz/" + КНИГИ[0],
        "..%2F..%2Fetc/" + КНИГИ[0],
    ],
)
def test_чужой_путь_404_без_журнала(среда, path):
    выгрузка(среда["dir"], "2026-09-30-100000-aaaa", КНИГИ, status="done", files=list(КНИГИ))

    assert браузер(1).get(f"/py/admin/exports/{path}").status_code == 404
    assert среда["журнал"] == []


def test_смотреть_можно_скачивать_нельзя(среда):
    выгрузка(среда["dir"], "2026-09-30-100000-aaaa", КНИГИ, status="done", files=list(КНИГИ))
    client = браузер(3)

    body = client.get("/py/admin/exports/").content.decode()

    assert "нет права скачивать" in body and "Выгрузить сейчас" not in body
    assert client.get(f"/py/admin/exports/2026-09-30-100000-aaaa/{КНИГИ[0]}").status_code == 403
    assert client.post("/py/admin/exports/").status_code == 403
    assert среда["журнал"] == [] and среда["запуски"] == []


def test_зависшая_считается_прерванной(среда):
    выгрузка(
        среда["dir"], "2026-09-30-100000-aaaa", status="running",
        started_at="2026-09-30T09:00:00+00:00",
    )  # fmt: skip

    assert exports.active() is None
    assert exports.all_runs()[0]["status"] == exports.FAILED
    body = браузер(1).get("/py/admin/exports/").content.decode()
    assert "не закончилась за 30 минут" in body and "disabled" not in body


def test_хранятся_последние(среда, monkeypatch):
    monkeypatch.setenv("EXPORTS_KEEP", "2")

    for n in range(4):
        выгрузка(среда["dir"], f"2026-09-3{n}-100000-aaaa", status="done")

    exports.prune()

    assert [r["id"] for r in exports.all_runs()] == [
        "2026-09-33-100000-aaaa",
        "2026-09-32-100000-aaaa",
    ]


class TestЗапуск:
    """exports.run: итог export_xlsx решает, отдаются ли книги."""

    @pytest.fixture
    def выгрузить(self, monkeypatch, среда):
        def fake(result: dict[str, Any] | None, books: int = 2):
            def call_command(name, *, dir, json, stdout, stderr):
                assert name == "export_xlsx" and json

                for book in КНИГИ[:books]:
                    Path(dir, book).write_bytes(b"PK")

                if result is not None:
                    stdout.write("таблица\n" + exports.RESULT + __import__("json").dumps(result))
                else:
                    stderr.write("Не удалось подключиться к базе")
                    raise SystemExit(1)

            monkeypatch.setattr("django.core.management.call_command", call_command)
            run_id = exports.create("консоль", None)
            assert run_id is not None
            exports.run(run_id)

            return exports.find(run_id), exports.books(run_id)

        return fake

    def test_сошлась(self, выгрузить):
        run, books = выгрузить({"self_check": True, "self_problems": []})

        assert run["status"] == exports.DONE and run["files"] == sorted(КНИГИ)
        assert books == sorted(КНИГИ) and run["python"]["status"] == "self"

    def test_не_сошлась_книги_не_отдаются(self, выгрузить):
        run, books = выгрузить({"self_check": False, "self_problems": ["Компании!C3"]})

        assert run["status"] == exports.FAILED and books == []
        assert run["note"] == "выгрузка не сошлась с базой"
        assert run["python"]["problems"] == ["Компании!C3"]

    def test_упала(self, выгрузить):
        run, books = выгрузить(None, books=1)

        assert run["status"] == exports.FAILED and books == []
        assert run["note"] == "выгрузка не удалась"
        assert "подключиться" in run["python"]["note"]


# ── Сквозная проверка на PostgreSQL ─────────────────────────────────


def test_кнопка_фон_и_скачивание_на_базе(tmp_path):
    from .pg_admin import АДРЕС, django, sql, свежая_база, сотрудник

    if not АДРЕС:
        pytest.skip("нет SAVDEX_PARITY_PG_URL — проверка требует PHP и PostgreSQL")

    свежая_база()
    admin = сотрудник("superadmin")
    sql(
        "insert into companies (name, slug, status, created_at, updated_at) values "
        "('ООО Проба', 'proba', 'active', now(), now())"
    )
    env = {"SAVDEX_EXPORTS_DIR": str(tmp_path)}

    [вход, запуск] = django(admin, ("post", "/py/admin/exports/", None), env=env)

    assert вход == 302 and запуск["status"] == 302
    [folder] = [p for p in tmp_path.iterdir() if p.is_dir()]
    run: dict[str, Any] = {}

    # Фоновый процесс: книги на пустой базе — секунды
    for _ in range(240):
        run = json.loads((folder / "run.json").read_text())

        if run["status"] in (exports.DONE, exports.FAILED):
            break

        time.sleep(0.5)

    assert run["status"] == exports.DONE, run
    assert run["requested_by"] == "Сотрудник superadmin" and len(run["files"]) == 2

    [_, страница, книга] = django(
        admin,
        ("get", "/py/admin/exports/", None),
        ("get", f"/py/admin/exports/{run['id']}/{run['files'][0]}", None),
        env=env,
    )

    assert страница["status"] == 200 and "готово" in страница["body"]
    assert книга["status"] == 200 and книга["body"].startswith("PK")
    assert sql(
        "select action, section, note from admin_actions where section = 'backups' order by id"
    ) == [
        ("exported", "backups", f"Выгрузка базы в Excel: {run['id']}"),
        ("downloaded", "backups", f"Скачан файл выгрузки {run['id']}/{run['files'][0]}"),
    ]
