"""Тревоги Grafana Cloud → Telegram-группа (docs/monitoring.md, шаг 3).

    python3 grafana-alerts.py check   # файл правил и ключи — ничего не меняет
    python3 grafana-alerts.py apply   # правила, шаблон, канал и маршрут — в Grafana

Правила — alerts.yaml рядом. apply кладёт в Grafana:
- папку SavdEx и группу правил в ней — целиком: правило, которого нет в
  файле, Grafana удаляет;
- шаблон сообщения и канал «SavdEx Telegram» (бот и группа);
- маршрут: все тревоги — в этот канал, повтор — по repeat_interval;
и пишет в группу, что тревоги обновлены. В Grafana всё это только для
чтения (загружено «из кода»): правка — в alerts.yaml, через PR.

Окружение:
  GRAFANA_URL         адрес стека, https://….grafana.net
  GRAFANA_SA_TOKEN    ключ сервисного аккаунта Grafana, роль Admin
  TELEGRAM_BOT_TOKEN  токен бота от @BotFather
  TELEGRAM_CHAT_ID    номер группы, с минусом
Значения ключей в журнал не выводятся: журнал Actions публичный.
"""

import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

import yaml

# Ответы Grafana и Telegram — разобранный JSON
Json = Any

RULES_FILE = Path(__file__).resolve().parent / "alerts.yaml"
KEYS = ("GRAFANA_URL", "GRAFANA_SA_TOKEN", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")
FOLDER_UID = "savdex"
TEMPLATE_NAME = "savdex"
CONTACT_UID = "savdex-telegram"
# Цифры агентов в Grafana Cloud: источник grafanacloud-<стек>-prom
DATASOURCE = re.compile(r"^grafanacloud-.+-prom$")
UID = re.compile(r"^[a-z0-9-]{1,40}$")
WHEN = re.compile(r"^\s*([<>])\s*(-?\d+(?:\.\d+)?)\s*$")
DURATION = re.compile(r"^(\d+)([smh])$")
SECONDS = {"s": 1, "m": 60, "h": 3600}
SEVERITY = {"critical", "warning"}
NO_DATA = {"ok": "OK", "alerting": "Alerting"}

# Сообщение в Telegram: по строке на тревогу. Пришла — summary правила,
# прошла — название и машина (summary к тому времени устарел: «диск
# заполнен на 87%»). Без разметки: в тексте бывают <, > и _
MESSAGE = """{{ define "savdex" -}}
{{ range .Alerts.Firing -}}
{{ if eq .Labels.severity "critical" }}🔴{{ else }}🟠{{ end }}
{{- " " }}{{ or .Annotations.summary .Labels.alertname }}
{{- with .Labels.rulename }} ({{ . }}){{ end }}
{{ end -}}
{{ range .Alerts.Resolved -}}
✅ Прошло: {{ .Labels.alertname }}{{ with .Labels.machine }} ({{ . }}){{ end }}
{{ end -}}
{{- end }}"""


class AlertsError(Exception):
    """Понятная ошибка для журнала: печатается без трассировки."""


def seconds(value: str, what: str) -> int:
    match = DURATION.match(str(value))
    if not match:
        raise AlertsError(f"{what}: «{value}» — нужна длительность вида 30s, 5m, 4h")
    return int(match.group(1)) * SECONDS[match.group(2)]


def load_rules() -> dict[str, Any]:
    """alerts.yaml с проверкой: ошибка в файле видна ещё на PR."""
    try:
        config = yaml.safe_load(RULES_FILE.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise AlertsError(f"{RULES_FILE.name}: не разбирается — {error}") from None
    if not isinstance(config, dict) or not isinstance(config.get("rules"), list):
        raise AlertsError(f"{RULES_FILE.name}: нужны настройки и список rules")

    for key in ("folder", "group", "interval", "contact_point", "repeat_interval", "rules"):
        if not config.get(key):
            raise AlertsError(f"{RULES_FILE.name}: нет «{key}»")
    seconds(config["interval"], "interval")
    seconds(config["repeat_interval"], "repeat_interval")

    seen: set[str] = set()
    for rule in config["rules"]:
        if not isinstance(rule, dict):
            raise AlertsError(f"{RULES_FILE.name}: правило — не набор полей: {rule!r}")
        name = rule.get("uid") or rule.get("title") or "?"
        for key in ("uid", "title", "expr", "when", "for", "severity", "summary"):
            if not rule.get(key):
                raise AlertsError(f"правило {name}: нет «{key}»")
        if not UID.match(rule["uid"]):
            raise AlertsError(f"правило {name}: uid — латиница, цифры и дефис, до 40 знаков")
        if rule["uid"] in seen:
            raise AlertsError(f"правило {name}: такой uid уже есть")
        seen.add(rule["uid"])
        if not WHEN.match(str(rule["when"])):
            raise AlertsError(f"правило {name}: when — «> число» или «< число»")
        seconds(rule["for"], f"правило {name}, for")
        if rule["severity"] not in SEVERITY:
            raise AlertsError(f"правило {name}: severity — critical или warning")
        if rule.get("no_data", "ok") not in NO_DATA:
            raise AlertsError(f"правило {name}: no_data — ok или alerting")
    rules: dict[str, Any] = config
    return rules


def build_rule(rule: dict[str, Any], datasource: str, group: str) -> dict[str, Any]:
    """Правило alerts.yaml → правило Grafana: запрос A, порог B."""
    op, value = WHEN.match(str(rule["when"])).groups()  # type: ignore[union-attr]
    return {
        "uid": rule["uid"],
        "title": rule["title"],
        "folderUID": FOLDER_UID,
        "ruleGroup": group,
        "condition": "B",
        "data": [
            {
                "refId": "A",
                "relativeTimeRange": {"from": 600, "to": 0},
                "datasourceUid": datasource,
                "model": {
                    "refId": "A",
                    "expr": rule["expr"].strip(),
                    "instant": True,
                    "range": False,
                    "datasource": {"type": "prometheus", "uid": datasource},
                },
            },
            {
                "refId": "B",
                "relativeTimeRange": {"from": 0, "to": 0},
                "datasourceUid": "__expr__",
                "model": {
                    "refId": "B",
                    "type": "threshold",
                    "expression": "A",
                    "datasource": {"type": "__expr__", "uid": "__expr__"},
                    "conditions": [
                        {
                            "evaluator": {
                                "type": "gt" if op == ">" else "lt",
                                "params": [float(value)],
                            }
                        }
                    ],
                },
            },
        ],
        "for": rule["for"],
        "noDataState": NO_DATA[rule.get("no_data", "ok")],
        # Grafana Cloud на минуту не ответил — не тревога: состояние прежнее
        "execErrState": "KeepLast",
        "annotations": {"summary": rule["summary"].strip()},
        "labels": {"severity": rule["severity"]},
        "isPaused": False,
    }


def request(
    url: str, method: str = "GET", body: object = None, headers: dict[str, str] | None = None
) -> tuple[int, Json]:
    data = None if body is None else json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as error:
        status, raw = error.code, error.read()
    except (urllib.error.URLError, TimeoutError) as error:
        # В тексте ошибки — только причина, без адреса: в адресе Telegram — токен
        reason = getattr(error, "reason", error)
        raise AlertsError(f"нет связи с {urllib.parse.urlsplit(url).hostname}: {reason}") from None
    try:
        return status, json.loads(raw) if raw else None
    except ValueError:
        return status, raw.decode(errors="replace")[:300]


class Grafana:
    def __init__(self, url: str, token: str) -> None:
        self.url = url.rstrip("/")
        self.token = token

    def call(self, method: str, path: str, body: object = None) -> tuple[int, Json]:
        return request(self.url + path, method, body, {"Authorization": f"Bearer {self.token}"})

    def must(self, method: str, path: str, body: object = None) -> Json:
        status, payload = self.call(method, path, body)
        if status >= 300:
            message = payload.get("message") if isinstance(payload, dict) else payload
            raise AlertsError(f"Grafana: {method} {path} — {status} {message}")
        return payload


class Telegram:
    def __init__(self, token: str, chat: str) -> None:
        api = os.environ.get("TELEGRAM_API", "https://api.telegram.org").rstrip("/")
        self.base = f"{api}/bot{token}"
        self.chat = chat

    def call(self, method: str, **params: object) -> Json:
        _, payload = request(f"{self.base}/{method}", "POST", params)
        if not isinstance(payload, dict) or not payload.get("ok"):
            description = payload.get("description") if isinstance(payload, dict) else payload
            raise AlertsError(f"Telegram {method}: {description}")
        return payload["result"]


def keys() -> dict[str, str]:
    values = {name: os.environ.get(name, "").strip() for name in KEYS}
    missing = [name for name, value in values.items() if not value]
    if missing:
        raise AlertsError(
            f"нет {', '.join(missing)} — GitHub → Settings → Secrets and variables → Actions"
            " (GRAFANA_URL — во Variables, остальное — в Secrets)"
        )
    if not re.match(r"^https?://[^/\s]+/?$", values["GRAFANA_URL"]):
        raise AlertsError("GRAFANA_URL — только адрес стека, вида https://имя.grafana.net")
    if not re.match(r"^-?\d+$", values["TELEGRAM_CHAT_ID"]):
        raise AlertsError("TELEGRAM_CHAT_ID — число, у группы — с минусом впереди")
    return values


def check_grafana(grafana: Grafana) -> str:
    """Ключ подходит, прав хватает; uid источника цифр."""
    status, _ = grafana.call("GET", "/api/folders?limit=1")
    if status == 401:
        raise AlertsError(
            "GRAFANA_SA_TOKEN не подходит: Grafana его не принимает"
            " (неверный, отозван или от другого стека)"
        )
    if status >= 300:
        raise AlertsError(f"Grafana по адресу GRAFANA_URL ответила {status} — тот ли адрес?")
    status, _ = grafana.call("GET", "/api/v1/provisioning/contact-points")
    if status == 403:
        raise AlertsError(
            "у ключа GRAFANA_SA_TOKEN нет прав на тревоги"
            " — у сервисного аккаунта должна быть роль Admin"
        )
    if status >= 300:
        raise AlertsError(f"Grafana: тревоги недоступны ({status})")

    sources = [s for s in grafana.must("GET", "/api/datasources") if s.get("type") == "prometheus"]
    found = [s for s in sources if DATASOURCE.match(s.get("name", ""))]
    if len(found) != 1:
        names = ", ".join(s.get("name", "?") for s in sources) or "нет"
        raise AlertsError(
            f"не найден один источник цифр grafanacloud-…-prom (источники Prometheus: {names})"
        )
    print(f"── Grafana {grafana.url}: ключ подходит, цифры — {found[0]['name']}")
    return str(found[0]["uid"])


def check_telegram(telegram: Telegram) -> None:
    try:
        bot = telegram.call("getMe")
    except AlertsError:
        raise AlertsError("TELEGRAM_BOT_TOKEN не подходит: Telegram не узнаёт бота") from None
    try:
        chat = telegram.call("getChat", chat_id=telegram.chat)
    except AlertsError as error:
        raise AlertsError(
            f"бот @{bot['username']} не видит группу TELEGRAM_CHAT_ID ({error}) — "
            "он добавлен в группу? номер — с минусом?"
        ) from None
    if chat.get("type") not in ("group", "supergroup"):
        raise AlertsError(
            f"TELEGRAM_CHAT_ID — не группа, а {chat.get('type')}: нужен номер группы, с минусом"
        )
    print(f"── Telegram: бот @{bot['username']}, группа «{chat.get('title')}»")


def apply(config: dict[str, Any], grafana: Grafana, telegram: Telegram, datasource: str) -> None:
    group = config["group"]
    contact = config["contact_point"]

    # Папка правил
    status, _ = grafana.call("GET", f"/api/folders/{FOLDER_UID}")
    if status == 404:
        grafana.must("POST", "/api/folders", {"uid": FOLDER_UID, "title": config["folder"]})
    elif status >= 300:
        raise AlertsError(f"Grafana: папка {FOLDER_UID} — {status}")

    # Шаблон сообщения и канал: бот и группа
    grafana.must("PUT", f"/api/v1/provisioning/templates/{TEMPLATE_NAME}", {"template": MESSAGE})
    point = {
        "uid": CONTACT_UID,
        "name": contact,
        "type": "telegram",
        "settings": {
            "bottoken": telegram_token(),
            "chatid": telegram.chat,
            "message": '{{ template "savdex" . }}',
            "parse_mode": "None",
            "disable_web_page_preview": True,
        },
        "disableResolveMessage": False,
    }
    existing = grafana.must("GET", "/api/v1/provisioning/contact-points")
    if any(p.get("uid") == CONTACT_UID for p in existing):
        grafana.must("PUT", f"/api/v1/provisioning/contact-points/{CONTACT_UID}", point)
    else:
        grafana.must("POST", "/api/v1/provisioning/contact-points", point)

    # Маршрут: все тревоги — в канал; вложенные маршруты, если их
    # заводили в Grafana, остаются
    tree = grafana.must("GET", "/api/v1/provisioning/policies")
    tree.update(
        {
            "receiver": contact,
            "group_by": ["grafana_folder", "alertname", "machine"],
            "group_wait": "30s",
            "group_interval": "5m",
            "repeat_interval": config["repeat_interval"],
        }
    )
    grafana.must("PUT", "/api/v1/provisioning/policies", tree)

    # Правила — группой целиком
    rules = [build_rule(rule, datasource, group) for rule in config["rules"]]
    path = f"/api/v1/provisioning/folder/{FOLDER_UID}/rule-groups/{urllib.parse.quote(group)}"
    interval = seconds(config["interval"], "interval")
    body = {"title": group, "folderUid": FOLDER_UID, "interval": interval, "rules": rules}
    grafana.must("PUT", path, body)
    loaded = grafana.must("GET", path)
    count = len(loaded.get("rules", []))
    if count != len(rules):
        raise AlertsError(f"Grafana: в группе {count} правил, а загружали {len(rules)}")
    print(f"── Загружено правил: {count}; канал «{contact}»")

    titles = "\n".join(f"• {rule['title']}" for rule in config["rules"])
    telegram.call(
        "sendMessage",
        chat_id=telegram.chat,
        text=f"✅ Тревоги SavdEx обновлены — {count} правил. Сюда придёт сообщение, когда:\n"
        + titles,
        disable_web_page_preview=True,
    )
    print("── Сообщение в группу отправлено")


def telegram_token() -> str:
    return os.environ["TELEGRAM_BOT_TOKEN"].strip()


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    if mode not in ("check", "apply"):
        print(__doc__, file=sys.stderr)
        return 2
    try:
        config = load_rules()
        print(f"── {RULES_FILE.name}: правил {len(config['rules'])}, разбирается")
        values = keys()
        grafana = Grafana(values["GRAFANA_URL"], values["GRAFANA_SA_TOKEN"])
        telegram = Telegram(values["TELEGRAM_BOT_TOKEN"], values["TELEGRAM_CHAT_ID"])
        datasource = check_grafana(grafana)
        check_telegram(telegram)
        if mode == "apply":
            apply(config, grafana, telegram, datasource)
    except AlertsError as error:
        print(f"::error title=Тревоги::{error}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
