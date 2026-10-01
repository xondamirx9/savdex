"""
Прозвон Uzum Checkout.

Ни один запрос наружу не уходит: транспорт поддельный. Проверка,
которая ходит в настоящий платёжный шлюз, — это либо запрос в боевую
кассу, либо падение без сети.

Значения маскировки — не по памяти: так маскировали прежние
UzumPing::mask и ::maskProxy, и вывод прозвона должен остаться прежним.
"""

from __future__ import annotations

import httpx
import pytest

from savdex.payments.uzum import (
    UzumConfig,
    UzumError,
    mask,
    mask_proxy,
    probe,
)

НАСТРОЕН = UzumConfig(
    enabled=True,
    checkout=True,
    sandbox=True,
    base_url="https://test-chk.uzum.uz",
    terminal_id="TERM-0001",
    secret_key="sk_test_0123456789abcdef",
    callback_login="login",
    callback_password="password",
    proxy="",
    spic="",
    package_code="",
    vat_percent=12,
    tin="",
)


def клиент(обработчик) -> httpx.Client:
    """Клиент с поддельным транспортом."""
    return httpx.Client(transport=httpx.MockTransport(обработчик))


def отвечает(тело: dict, status: int = 200):
    return lambda _: httpx.Response(status, json=тело)


class TestМаскировкаКлючей:
    @pytest.mark.parametrize(
        ("значение", "ожидается"),
        [
            ("", "(пусто)"),
            ("a", "*"),
            ("ab", "**"),
            ("abcdef", "******"),
            ("abcdefg", "abc***efg"),
            ("abcdefgh", "abc***fgh"),
            ("1234567890", "123****890"),
            ("sk_live_51H8xQ2", "sk_*********xQ2"),
            ("ключ-по-русски", "клю********ски"),
            ("x" * 40, "xxx" + "*" * 34 + "xxx"),
        ],
    )
    def test_маска(self, значение, ожидается):
        assert mask(значение) == ожидается

    def test_короткий_ключ_закрыт_целиком(self):
        """У шестизначного «первые три и последние три» не скрывает ничего."""
        assert mask("abcdef") == "******"
        assert "a" not in mask("abcdef")


class TestМаскировкаПрокси:
    @pytest.mark.parametrize(
        ("значение", "ожидается"),
        [
            ("", "(пусто — прямое соединение)"),
            ("http://proxy.example.com:8080", "http://proxy.example.com:8080"),
            (
                "http://user:secret@proxy.example.com:8080",
                "http://user:***@proxy.example.com:8080",
            ),
            ("socks5://login:12345@10.0.0.1:1080", "socks5://login:***@10.0.0.1:1080"),
            ("http://noauth@proxy:8080", "http://noauth@proxy:8080"),
        ],
    )
    def test_маска_прокси(self, значение, ожидается):
        assert mask_proxy(значение) == ожидается

    def test_пароль_с_собакой_не_утекает(self):
        """
        Расхождение с PHP-версией, и намеренное.

        Её выражение обрывается на первом `@`, и пароль вида `p@ss:word`
        попадал в вывод хвостом: «http://user:***@ss:word@host». Прозвон
        печатают в задачу и присылают в переписку — это утечка, пусть
        и редкая.
        """
        закрыто = mask_proxy("http://user:p@ss:word@proxy.host:3128")

        assert закрыто == "http://user:***@proxy.host:3128"
        assert "ss:word" not in закрыто

    def test_адрес_с_путём_не_ломается(self):
        assert mask_proxy("http://user:secret@proxy:8080/path") == "http://user:***@proxy:8080/path"


class TestПрозвон:
    def test_заказ_не_найден_значит_всё_хорошо(self):
        """
        3005 — удача, а не сбой.

        Заказа с придуманным номером и не должно существовать. Ответ
        означает ровно то, ради чего прозвон делается: сеть открыта,
        терминал и ключ приняты.
        """
        итог = probe(
            НАСТРОЕН,
            клиент(отвечает({"errorCode": 3005, "message": "Order not found"})),
        )

        assert итог.ok is True
        assert "терминал и ключ приняты" in итог.message
        assert "код 3005" in итог.message

    def test_второй_хороший_код(self):
        итог = probe(НАСТРОЕН, клиент(отвечает({"errorCode": 3035, "message": "Done"})))

        assert итог.ok is True

    @pytest.mark.parametrize("код", [1000, 1003, 1999])
    def test_ключи_отвергнуты(self, код):
        итог = probe(НАСТРОЕН, клиент(отвечает({"errorCode": код, "message": "Auth"})))

        assert итог.ok is False
        assert "ключи отвергнуты" in итог.message
        assert "PAYMENTS_UZUM_TERMINAL_ID" in итог.message

    @pytest.mark.parametrize("код", [999, 2000, 3006])
    def test_чужой_код_отдаётся_как_есть(self, код):
        """Незнакомый отказ не выдаётся за понятный."""
        итог = probe(НАСТРОЕН, клиент(отвечает({"errorCode": код, "message": "Что-то"})))

        assert итог.ok is False
        assert итог.message == f"Uzum отказал: код {код}, Что-то"

    def test_сеть_закрыта(self):
        """Самый частый затык: адреса площадки нет в белом списке Uzum."""

        def обрыв(request):
            raise httpx.ConnectTimeout("timed out", request=request)

        итог = probe(НАСТРОЕН, клиент(обрыв))

        assert итог.ok is False
        assert "не в белом списке" in итог.message

    def test_http_не_двести(self):
        итог = probe(НАСТРОЕН, клиент(отвечает({}, status=502)))

        assert итог.ok is False
        assert "HTTP 502" in итог.message

    def test_не_json(self):
        """Страница-заглушка прокси вместо ответа API."""
        итог = probe(
            НАСТРОЕН,
            клиент(lambda _: httpx.Response(200, text="<html>Gateway</html>")),
        )

        assert итог.ok is False
        assert "не-JSON" in итог.message

    def test_нулевой_код_тоже_успех(self):
        итог = probe(НАСТРОЕН, клиент(отвечает({"errorCode": 0, "result": {}})))

        assert итог.ok is True
        assert итог.message == "API Uzum доступен, ключи приняты"

    @pytest.mark.parametrize(
        ("поле", "переменная"),
        [
            ("base_url", "PAYMENTS_UZUM_BASE_URL"),
            ("terminal_id", "PAYMENTS_UZUM_TERMINAL_ID"),
            ("secret_key", "PAYMENTS_UZUM_SECRET_KEY"),
        ],
    )
    def test_незаполненная_настройка_названа_поимённо(self, поле, переменная):
        """«Не настроено» без имени переменной заставляет гадать."""
        неполный = UzumConfig(**{**НАСТРОЕН.__dict__, поле: ""})

        def нельзя_ходить(request):
            raise AssertionError("запрос ушёл, хотя настроек не хватает")

        итог = probe(неполный, клиент(нельзя_ходить))

        assert итог.ok is False
        assert переменная in итог.message

    def test_кириллица_в_ключе_объясняется(self):
        """
        Русская «с» вместо латинской «c» видна разве что под лупой.

        Без разбора этого случая команда, вся работа которой —
        объяснять, что не так, падала бы трассировкой UnicodeEncodeError.
        """
        с_опечаткой = UzumConfig(**{**НАСТРОЕН.__dict__, "secret_key": "sk_тест_123"})

        итог = probe(с_опечаткой, клиент(отвечает({"errorCode": 0})))

        assert итог.ok is False
        assert "не из латиницы" in итог.message
        assert "PAYMENTS_UZUM_SECRET_KEY" in итог.message

    def test_запрос_несёт_ключи_в_заголовках(self):
        увиденное = {}

        def запомнить(request):
            увиденное["terminal"] = request.headers.get("X-Terminal-Id")
            увиденное["key"] = request.headers.get("X-API-Key")
            увиденное["path"] = request.url.path

            return httpx.Response(200, json={"errorCode": 3005, "message": "нет"})

        probe(НАСТРОЕН, клиент(запомнить))

        assert увиденное["terminal"] == "TERM-0001"
        assert увиденное["key"] == "sk_test_0123456789abcdef"
        assert увиденное["path"] == "/api/v1/payment/getOrderStatus"


class TestНастройкиИзОкружения:
    def test_читаются_переменные_payments_uzum(self, monkeypatch):
        monkeypatch.setenv("PAYMENTS_UZUM_ENABLED", "true")
        monkeypatch.setenv("PAYMENTS_UZUM_BASE_URL", "https://chk.uzum.uz")
        monkeypatch.setenv("PAYMENTS_UZUM_TERMINAL_ID", "T-1")
        monkeypatch.setenv("PAYMENTS_UZUM_VAT_PERCENT", "0")

        config = UzumConfig.from_env()

        assert config.enabled is True
        assert config.base_url == "https://chk.uzum.uz"
        assert config.terminal_id == "T-1"
        assert config.vat_percent == 0

    def test_умолчания_как_в_config_payments(self, monkeypatch):
        """
        Незаданный контур — тестовый.

        Умолчание sandbox=true в config/payments.php стоит нарочно:
        забытая переменная должна увести в песочницу, а не в боевую кассу.
        """
        for имя in ("PAYMENTS_UZUM_ENABLED", "PAYMENTS_UZUM_SANDBOX"):
            monkeypatch.delenv(имя, raising=False)

        config = UzumConfig.from_env()

        assert config.enabled is False
        assert config.sandbox is True
        assert config.vat_percent == 12

    def test_секреты_в_выводе_не_печатаются(self):
        """
        Сторожевая проверка.

        Прозвон печатают в задачу и присылают в переписку. Ключ,
        попавший в вывод целиком, — это ключ, который надо менять.
        Так уже было с APP_KEY в сентябре.
        """
        config = UzumConfig(
            **{
                **НАСТРОЕН.__dict__,
                "secret_key": "sk_live_НАСТОЯЩИЙ_КЛЮЧ",
                "callback_password": "пароль-колбэка",
                "proxy": "http://user:пароль-прокси@10.0.0.1:3128",
            }
        )

        вывод = "\n".join(config.lines())

        assert "sk_live_НАСТОЯЩИЙ_КЛЮЧ" not in вывод
        assert "пароль-колбэка" not in вывод
        assert "пароль-прокси" not in вывод
        # Но узнать ключ по краям всё-таки можно — иначе нечем сверить,
        # тот ли ключ задан
        assert "sk_" in вывод
        assert "10.0.0.1:3128" in вывод


class TestОшибка:
    def test_код_едет_полем_а_не_в_тексте(self):
        """
        Расхождение с PHP-версией.

        Та собирает русскую фразу и разбирает её обратно регулярным
        выражением. Перевод сообщения сломал бы разбор молча.
        """
        error = UzumError("Uzum отказал: код 3005, Order not found", code=3005)

        assert error.code == 3005

    def test_без_кода_когда_до_ответа_не_дошло(self):
        assert UzumError("Uzum недоступен: timed out").code is None
