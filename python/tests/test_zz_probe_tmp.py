"""TEMP probe — delete me."""
from __future__ import annotations
import json, subprocess, sys
from .factories import компания, объявление, it_задача, тендер, пользователь as фпользователь
from .pg_admin import PYTHON, ОКРУЖЕНИЕ, sql, свежая_база, нужна_база
from .web_site import САЙТ, адрес, вход, пользователь, _манифест

pytestmark = нужна_база
OUT = "/tmp/claude-0/-home-user-savdex/686f4bf9-3041-53ce-b493-0adab1252eee/scratchpad/probe_env.json"

def test_setup():
    свежая_база()
    subprocess.run([sys.executable, "manage.py", "seed", "--fresh"], cwd=PYTHON,
        env={**ОКРУЖЕНИЕ, "DJANGO_DATABASE_URL": ОКРУЖЕНИЕ["DB_URL"], "DJANGO_SETTINGS_MODULE": "savdex.settings", "PYTHONPATH": str(PYTHON)},
        capture_output=True, check=True)
    c = компания(slug="owner")
    other = компания(slug="other")
    l = объявление(company_id=c, slug="cement")
    объявление(company_id=other, slug="other-l")
    t = it_задача(company_id=c, slug="task")
    тендер(slug="tender1")
    uid = пользователь("owner@example.com", company_id=c, company_role="owner")
    uid2 = пользователь("nocomp@example.com")
    sql("insert into resumes (user_id, title, status, slug, created_at, updated_at) values (%s,'Dev','published','dev',now(),now())", [uid2])
    cook = вход(uid)
    cook2 = вход(uid2)
    with адрес() as root:
        env = {**ОКРУЖЕНИЕ, **САЙТ, "APP_URL": root, "DJANGO_SETTINGS_MODULE": "savdex.settings", "PYTHONPATH": str(PYTHON)}
        json.dump({"env": env, "root": root, "owner": cook, "nocomp": cook2, "listing": l, "task": t, "company": c}, open(OUT, "w"))
