"""
Uzum Checkout: настройки, маскировка секретов и прозвон API.

Перенос `savdex:uzum-ping` из PHP — неделя 2 этапа 1
(`docs/migration-to-python.md`, раздел 8). Ни одного платежа здесь
не проводится и ни одной строки в базу не пишется: команда спрашивает
у Uzum статус несуществующего заказа и по ответу говорит, где затык —
сеть, ключи или конфигурация.

Деньги переезжают на Django последними, этапом 7. Эта команда идёт
раньше всех именно потому, что к деньгам не прикасается: она про сеть,
секреты и настройки — то, на чём в новой половине площадки ещё никто
не обжигался.

## Чем отличается от PHP-версии

**Ошибка несёт код, а не прячет его в текст.** PHP-версия собирает
русскую фразу «Uzum отказал: код 3005, …» и потом разбирает её
обратно регулярным выражением. Здесь код едет отдельным полем
исключения, а фразы остаются те же, слово в слово. Разбирать
собственный текст, чтобы узнать то, что было известно на строчку
выше, — способ однажды сломать проверку переводом сообщения.

**Пароль прокси маскируется целиком.** Выражение PHP-версии
обрывается на первом `@`, и пароль вида `p@ss:word` попадал в вывод
хвостом: `http://user:***@ss:word@host`. Прозвон печатают в задачу
и присылают в переписку, так что это настоящая утечка, пусть
и редкая. Здесь маскируется всё до последнего `@`. На правильно
закодированном адресе (`%40` вместо `@`) вывод прежний.

Остальное построчно то же, вплоть до звёздочек в ключах.
"""

from __future__ import annotations

import os
import re
import uuid
from dataclasses import dataclass

import httpx

#: Заказ не найден / уже обработан. Для прозвона это удача: значит
#: сеть открыта, терминал и ключ приняты
ХОРОШИЕ_КОДЫ = (3005, 3035)

ПУТЬ_СТАТУСА = "/api/v1/payment/getOrderStatus"

# Те же, что у PHP-версии: connectTimeout(5)->timeout(15)
СВЯЗЬ = httpx.Timeout(15.0, connect=5.0)


class UzumError(Exception):
    """
    Отказ Uzum или обрыв связи.

    `code` — errorCode из ответа, если он был. None означает, что
    до разбора ответа дело не дошло: не хватило настроек, не открылась
    сеть, пришёл не-JSON.
    """

    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)

        self.code = code


def mask(value: str) -> str:
    """
    Секрет в выводе — только краями.

    Перенесено из App\\Console\\Commands\\UzumPing::mask. Короткие
    значения закрываются целиком: у шестизначного ключа «первые три
    и последние три» не скрывает ничего.
    """
    if value == "":
        return "(пусто)"

    if len(value) <= 6:
        return "*" * len(value)

    return value[:3] + "*" * max(3, len(value) - 6) + value[-3:]


def mask_proxy(value: str) -> str:
    """
    Адрес прокси без пароля: host:port виден, пароль — нет.

    До последнего `@`, а не до первого (см. заголовок модуля).
    """
    if value == "":
        return "(пусто — прямое соединение)"

    return re.sub(r"//([^:@/]+):[^/]*@", r"//\1:***@", value)


@dataclass(frozen=True)
class UzumConfig:
    """Настройки провайдера. Имена переменных те же, что у Laravel."""

    enabled: bool
    checkout: bool
    sandbox: bool
    base_url: str
    terminal_id: str
    secret_key: str
    callback_login: str
    callback_password: str
    proxy: str
    spic: str
    package_code: str
    vat_percent: int
    tin: str

    @classmethod
    def from_env(cls) -> UzumConfig:
        def флаг(name: str, default: str = "false") -> bool:
            return os.environ.get(name, default).strip().lower() in ("1", "true", "yes", "on")

        def строка(name: str) -> str:
            return os.environ.get(name, "").strip()

        def число(name: str, default: int) -> int:
            try:
                return int(os.environ.get(name, "") or default)
            except ValueError:
                return default

        return cls(
            enabled=флаг("PAYMENTS_UZUM_ENABLED"),
            checkout=флаг("PAYMENTS_UZUM_CHECKOUT_ENABLED"),
            # Умолчание true, как в config/payments.php: незаданный
            # контур означает тестовый, а не боевой
            sandbox=флаг("PAYMENTS_UZUM_SANDBOX", "true"),
            base_url=строка("PAYMENTS_UZUM_BASE_URL"),
            terminal_id=строка("PAYMENTS_UZUM_TERMINAL_ID"),
            secret_key=строка("PAYMENTS_UZUM_SECRET_KEY"),
            callback_login=строка("PAYMENTS_UZUM_CALLBACK_LOGIN"),
            callback_password=строка("PAYMENTS_UZUM_CALLBACK_PASSWORD"),
            proxy=строка("PAYMENTS_UZUM_PROXY"),
            spic=строка("PAYMENTS_UZUM_SPIC"),
            package_code=строка("PAYMENTS_UZUM_PACKAGE_CODE"),
            vat_percent=число("PAYMENTS_UZUM_VAT_PERCENT", 12),
            tin=строка("PAYMENTS_UZUM_TIN"),
        )

    def lines(self) -> list[str]:
        """Настройки для вывода — секреты уже закрыты."""
        да_нет = {True: "true", False: "false"}

        return [
            f"PAYMENTS_UZUM_ENABLED           = {да_нет[self.enabled]}",
            f"PAYMENTS_UZUM_CHECKOUT_ENABLED  = {да_нет[self.checkout]}",
            f"PAYMENTS_UZUM_SANDBOX           = {да_нет[self.sandbox]}",
            f"PAYMENTS_UZUM_BASE_URL          = {self.base_url or '(пусто)'}",
            f"PAYMENTS_UZUM_TERMINAL_ID       = {mask(self.terminal_id)}",
            f"PAYMENTS_UZUM_SECRET_KEY        = {mask(self.secret_key)}",
            f"PAYMENTS_UZUM_CALLBACK_LOGIN    = {mask(self.callback_login)}",
            f"PAYMENTS_UZUM_CALLBACK_PASSWORD = {mask(self.callback_password)}",
            f"PAYMENTS_UZUM_PROXY             = {mask_proxy(self.proxy)}",
            f"PAYMENTS_UZUM_SPIC              = {self.spic or '(пусто — корзина не передаётся)'}",
            f"PAYMENTS_UZUM_PACKAGE_CODE      = {self.package_code or '(пусто)'}",
            f"PAYMENTS_UZUM_VAT_PERCENT       = {self.vat_percent}",
            f"PAYMENTS_UZUM_TIN               = {self.tin or '(пусто)'}",
        ]


@dataclass(frozen=True)
class Probe:
    ok: bool
    message: str


def _request(config: UzumConfig, client: httpx.Client) -> dict[str, object]:
    """
    Один запрос к Uzum. Возвращает `result`, иначе бросает UzumError.

    Разбор ответа повторяет UzumGateway::unwrap: HTTP 200 и errorCode 0,
    всё остальное — отказ.
    """
    try:
        ответ = client.post(
            config.base_url.rstrip("/") + ПУТЬ_СТАТУСА,
            json={"orderId": str(uuid.uuid4())},
            headers={
                "X-Terminal-Id": config.terminal_id,
                "X-API-Key": config.secret_key,
                # Язык платёжной формы. У прозвона локали нет, и это
                # всегда ru-RU — форму никому не показывают
                "Content-Language": "ru-RU",
                "Accept": "application/json",
            },
        )
    except httpx.RequestError as error:
        raise UzumError(f"Uzum недоступен: {error}") from error
    except UnicodeEncodeError as error:
        # Заголовки HTTP — только латиница. Кириллица в ключе означает
        # опечатку при копировании из документа: русская «с» вместо
        # латинской «c» видна разве что под лупой. Без этой ветки
        # диагностическая команда падает трассировкой вместо ответа
        raise UzumError(
            "В терминале или ключе есть символы не из латиницы — "
            "заголовки HTTP их не принимают. Скорее всего, при копировании "
            "затесалась кириллица: проверьте PAYMENTS_UZUM_TERMINAL_ID "
            "и PAYMENTS_UZUM_SECRET_KEY."
        ) from error

    if ответ.status_code != httpx.codes.OK:
        raise UzumError(f"Uzum ответил HTTP {ответ.status_code}")

    try:
        тело = ответ.json()
    except ValueError as error:
        raise UzumError("Uzum вернул не-JSON ответ") from error

    if not isinstance(тело, dict):
        raise UzumError("Uzum вернул не-JSON ответ")

    код = int(тело.get("errorCode", -1))

    if код != 0:
        описание = str(тело.get("message", "без описания"))

        raise UzumError(f"Uzum отказал: код {код}, {описание}", code=код)

    результат = тело.get("result", {})

    return результат if isinstance(результат, dict) else {}


def probe(config: UzumConfig, client: httpx.Client | None = None) -> Probe:
    """
    Прозвон без платежа: статус несуществующего заказа.

    Читается по ответу: коды 3005/3035 — сеть открыта и ключи приняты;
    коды 1xxx — сеть открыта, ключи отвергнуты; обрыв связи — нашего
    адреса нет в белом списке Uzum.

    Клиент принимается снаружи, чтобы проверки подставляли поддельный
    транспорт: прозвон, который в тестах ходит в настоящий Uzum, —
    это либо запрос в боевой платёжный шлюз, либо проверка, падающая
    без сети.
    """
    не_хватает = [
        имя for имя in ("base_url", "terminal_id", "secret_key") if not getattr(config, имя)
    ]

    if не_хватает:
        ключ = не_хватает[0]

        return Probe(
            ok=False,
            message=(
                f"Uzum не настроен: не задан ключ «{ключ}» "
                f"(переменная окружения PAYMENTS_UZUM_{ключ.upper()})"
            ),
        )

    свой_клиент = client is None
    client = client or httpx.Client(timeout=СВЯЗЬ, proxy=config.proxy or None)

    try:
        _request(config, client)
    except UzumError as error:
        return _объяснить(error)
    finally:
        if свой_клиент:
            client.close()

    # errorCode 0 на несуществующий заказ — странно, но доступ есть
    return Probe(ok=True, message="API Uzum доступен, ключи приняты")


def _объяснить(error: UzumError) -> Probe:
    """
    Что означает отказ.

    Разбор по коду, а не по тексту сообщения (см. заголовок модуля).
    Сами формулировки — те же, что у PHP-версии: человек, который
    однажды их читал, не должен разбираться заново.
    """
    сообщение = str(error)

    if error.code in ХОРОШИЕ_КОДЫ:
        return Probe(
            ok=True,
            message=f"API Uzum доступен, терминал и ключ приняты ({сообщение})",
        )

    if error.code is not None and 1000 <= error.code <= 1999:
        return Probe(
            ok=False,
            message=(
                "API доступен, но ключи отвергнуты — проверьте "
                f"PAYMENTS_UZUM_TERMINAL_ID и PAYMENTS_UZUM_SECRET_KEY ({сообщение})"
            ),
        )

    if "недоступен" in сообщение:
        return Probe(
            ok=False,
            message=(
                "До API Uzum не достучаться — наш адрес не в белом списке "
                f"или неверен PAYMENTS_UZUM_BASE_URL ({сообщение})"
            ),
        )

    return Probe(ok=False, message=сообщение)
