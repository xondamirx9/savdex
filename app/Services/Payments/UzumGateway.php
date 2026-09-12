<?php

declare(strict_types=1);

namespace App\Services\Payments;

use App\Models\Payment;
use App\Models\PaymentMethod;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\PendingRequest;
use Illuminate\Http\Client\Response as HttpResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Response;

/**
 * Uzum Checkout — онлайн-касса: регистрация платежа и увод покупателя
 * на платёжную страницу Uzum.
 *
 * Это второй продукт Uzum рядом с Merchant API (тот принимает оплату
 * из приложения Uzum Bank и живёт в UzumMerchantController). Checkout
 * работает наоборот: наш сервер сам зовёт Uzum — /payment/register
 * создаёт платёж и возвращает ссылку платёжной формы, покупатель
 * платит картой, Uzum шлёт колбэк на /payments/uzum/callback.
 *
 * Аутентификация исходящих запросов — заголовки X-Terminal-Id и
 * X-API-Key (config: terminal_id и secret_key). Суммы — в тийинах.
 *
 * Колбэк Checkout не подписан, поэтому доверять ему нельзя: перед
 * начислением статус платежа переспрашивается у Uzum методом
 * /payment/getOrderStatus (авторизован нашим ключом) и начисление
 * происходит только при подтверждённом COMPLETED. Счёт ищется по
 * external_id (orderId, который Uzum выдал на нашу же регистрацию),
 * а не по номеру счёта из тела колбэка — подделать связку нельзя.
 */
class UzumGateway implements PaymentGateway
{
    /** Узбекский сум по ISO 4217 — единственная валюта Checkout. */
    private const CURRENCY_UZS = 860;

    /** Максимум, что разрешает протокол: 30 минут на оплату формы. */
    private const SESSION_TIMEOUT_SECS = 1800;

    /** Статус заказа Uzum, при котором деньги действительно списаны. */
    private const ORDER_COMPLETED = 'COMPLETED';

    /**
     * Где в result может лежать ссылка платёжной страницы: имя поля
     * в документации не зафиксировано (пример свёрнут), поэтому
     * перебираются известные варианты.
     */
    private const PAY_URL_KEYS = ['paymentRedirectUrl', 'redirectUrl', 'paymentUrl', 'payUrl', 'formUrl', 'url'];

    /** @param array<string, mixed> $config */
    public function __construct(private readonly array $config) {}

    public function provider(): string
    {
        return 'uzum';
    }

    public function createCheckout(Payment $payment, array $options = []): array
    {
        $this->require(['base_url', 'terminal_id', 'secret_key']);

        $returnUrl = (string) ($this->config['return_url'] ?? '');

        $result = $this->post('/api/v1/payment/register', [
            'amount' => $payment->amountMinor(),
            'clientId' => (string) $payment->company_id,
            'currency' => self::CURRENCY_UZS,
            'paymentDetails' => mb_substr((string) $payment->description, 0, 1024),
            'orderNumber' => mb_substr($payment->number, 0, 36),
            'sessionTimeoutSecs' => self::SESSION_TIMEOUT_SECS,
            'viewType' => 'REDIRECT',
            'successUrl' => $returnUrl,
            'failureUrl' => $returnUrl,
            'paymentParams' => [
                'operationType' => 'PAYMENT',
                'payType' => 'ONE_STEP',
            ],
            ...$this->fiscalCart($payment),
        ]);

        $orderId = $result['orderId'] ?? null;
        $payUrl = $this->paymentPageUrl($result);

        if (! is_string($orderId) || $orderId === '' || $payUrl === null) {
            // Весь result целиком: секретов в нём нет, а имя поля со
            // ссылкой в документации не зафиксировано — по логу видно,
            // как его назвал Uzum
            Log::warning('payment.uzum.register_unexpected', ['result' => $result]);

            throw new PaymentGatewayException('Uzum зарегистрировал платёж, но не вернул orderId или ссылку оплаты');
        }

        Log::info('payment.uzum.registered', ['order' => $orderId, 'payment' => $payment->number]);

        // orderId — единственный надёжный мост между колбэком и счётом:
        // колбэк не подписан, и найтись счёт должен по идентификатору,
        // который выдал сам Uzum на нашу регистрацию
        $payment->fill(['external_id' => $orderId])->save();

        return ['redirect_url' => $payUrl, 'order_id' => $orderId];
    }

    /**
     * Колбэком Checkout признаётся тело с orderId и operationState.
     * Подписи у колбэка нет; если Uzum сообщил IP своих колбэков
     * (callback_ips), запрос сверяется и с ними.
     */
    public function verifyCallback(Request $request): bool
    {
        $ips = $this->config['callback_ips'] ?? [];

        if ($ips !== [] && ! in_array($request->ip(), $ips, true)) {
            return false;
        }

        $orderId = $request->json('orderId');
        $state = $request->json('operationState');

        return is_string($orderId) && $orderId !== '' && is_string($state) && $state !== '';
    }

    public function parseCallback(Request $request): array
    {
        /** @var array<string, mixed> $data */
        $data = $request->json()->all();
        $orderId = (string) ($data['orderId'] ?? '');
        $state = strtoupper((string) ($data['operationState'] ?? ''));

        if ($state === 'SUCCESS' && ! $this->orderCompleted($orderId)) {
            // Начислять по неподтверждённому успеху нельзя. Исключение
            // превращается в ответ 400 — Uzum повторит колбэк (до 5 раз),
            // и временный сбой getOrderStatus не потеряет оплату
            throw new PaymentGatewayException("Uzum сообщил об оплате {$orderId}, но getOrderStatus не подтвердил COMPLETED");
        }

        return [
            // Неуспех попытки — не отмена счёта: покупатель может
            // попробовать другую карту или заплатить переводом, поэтому
            // всё, кроме подтверждённого успеха, отдаётся как pending
            'status' => $state === 'SUCCESS' ? 'paid' : 'pending',
            'reference' => $orderId,
            'provider_transaction_id' => $orderId,
            'amount_minor' => null,
            'raw' => $data,
        ];
    }

    public function callbackResponse(bool $accepted, array $event): Response
    {
        // Uzum ждёт 200 OK как подтверждение доставки; всё остальное
        // (до 5 повторов) — сигнал прислать колбэк ещё раз. 99999 —
        // «сервис недоступен» из номенклатуры Merchant API: на базовый
        // адрес забредают и его вызовы, им нужен ответ в их формате
        return new JsonResponse([
            'status' => $accepted ? 'OK' : 'FAILED',
            'errorCode' => $accepted ? null : 99999,
        ], $accepted ? 200 : 400);
    }

    public function chargeSavedCard(Payment $payment, PaymentMethod $card): array
    {
        // TODO(uzum-checkout): регистрация через /payment/register и
        // списание /payment/merchantPay с type=bind — когда в кабинете
        // появится привязка карт (operationType=BINDING).
        throw new PaymentGatewayException('Оплата привязанной картой Uzum ещё не подключена');
    }

    public function refund(Payment $payment, int $amountMinor): array
    {
        // TODO(uzum-checkout): /api/v1/acquiring/refund с X-Operation-Id
        // (ключ идемпотентности) — когда возвраты понадобятся в админке.
        throw new PaymentGatewayException('Возврат через Uzum ещё не подключён — оформите возврат в кабинете Uzum');
    }

    /**
     * Корзина для автофискализации — одна позиция на всю сумму счёта.
     *
     * Uzum с включённой автофискализацией отвечает 3045 без корзины;
     * без ИКПУ в конфиге корзина не передаётся вовсе — терминал без
     * фискализации на лишнее поле может ответить 3058.
     *
     * @return array<string, mixed>
     */
    private function fiscalCart(Payment $payment): array
    {
        $fiscal = (array) ($this->config['fiscal'] ?? []);
        $spic = trim((string) ($fiscal['spic'] ?? ''));

        if ($spic === '') {
            return [];
        }

        $amount = $payment->amountMinor();

        return ['merchantParams' => ['cart' => [
            'cartId' => $payment->number,
            'receiptType' => 'PURCHASE',
            'total' => $amount,
            'items' => [[
                'productId' => $payment->purpose.'-'.($payment->plan_id ?? $payment->credit_pack_id ?? $payment->id),
                'title' => mb_substr((string) ($payment->description ?: 'Услуги площадки SAVDEX'), 0, 255),
                'quantity' => 1,
                'price' => $amount,
                'total' => $amount,
                'spic' => $spic,
                'packageCode' => (string) ($fiscal['package_code'] ?? ''),
                'vatPercent' => (int) ($fiscal['vat_percent'] ?? 0),
            ]],
        ]]];
    }

    /**
     * Прозвон без денег: доступен ли API и принимает ли он наши ключи.
     *
     * Спрашивается статус заведомо несуществующего заказа. Ответ
     * «платёж не найден» (3005/3035) означает, что сеть открыта и
     * ключи приняты; ошибки 1xxx — сеть открыта, ключи отвергнуты;
     * таймаут — наш адрес не в белом списке Uzum.
     *
     * @return array{ok: bool, message: string}
     */
    public function probe(): array
    {
        try {
            $this->require(['base_url', 'terminal_id', 'secret_key']);
            $this->post('/api/v1/payment/getOrderStatus', ['orderId' => (string) Str::uuid()]);
        } catch (PaymentGatewayException $e) {
            $message = $e->getMessage();

            if (preg_match('/код (3005|3035)\b/u', $message)) {
                return ['ok' => true, 'message' => 'API Uzum доступен, терминал и ключ приняты ('.$message.')'];
            }

            if (preg_match('/код 1\d{3}\b/u', $message)) {
                return ['ok' => false, 'message' => 'API доступен, но ключи отвергнуты — проверьте PAYMENTS_UZUM_TERMINAL_ID и PAYMENTS_UZUM_SECRET_KEY ('.$message.')'];
            }

            if (str_contains($message, 'недоступен')) {
                return ['ok' => false, 'message' => 'До API Uzum не достучаться — наш адрес не в белом списке или неверен PAYMENTS_UZUM_BASE_URL ('.$message.')'];
            }

            return ['ok' => false, 'message' => $message];
        }

        // errorCode 0 на несуществующий заказ — странно, но доступ есть
        return ['ok' => true, 'message' => 'API Uzum доступен, ключи приняты'];
    }

    // ── Внутреннее ───────────────────────────────────────────

    /** Списаны ли деньги по заказу — спрашиваем сам Uzum, а не колбэк. */
    private function orderCompleted(string $orderId): bool
    {
        if ($orderId === '') {
            return false;
        }

        try {
            $this->require(['base_url', 'terminal_id', 'secret_key']);
            $result = $this->post('/api/v1/payment/getOrderStatus', [
                'orderId' => $orderId,
            ]);
        } catch (PaymentGatewayException $e) {
            Log::warning('payment.uzum.status_check_failed', ['order' => $orderId, 'message' => $e->getMessage()]);

            return false;
        }

        // Имя поля статуса в result документация не фиксирует —
        // принимаются очевидные варианты, в том числе вложенные
        foreach (['status', 'orderStatus', 'state', 'paymentStatus', 'operationState'] as $key) {
            if (strtoupper((string) ($result[$key] ?? '')) === self::ORDER_COMPLETED) {
                return true;
            }
        }

        foreach ($result as $value) {
            if (is_array($value) && $this->hasCompletedStatus($value)) {
                return true;
            }
        }

        Log::warning('payment.uzum.status_unrecognized', ['order' => $orderId, 'result' => $result]);

        return false;
    }

    /** @param array<string, mixed> $node */
    private function hasCompletedStatus(array $node): bool
    {
        foreach (['status', 'orderStatus', 'state', 'paymentStatus', 'operationState'] as $key) {
            if (strtoupper((string) ($node[$key] ?? '')) === self::ORDER_COMPLETED) {
                return true;
            }
        }

        return false;
    }

    /**
     * POST к API Uzum: сетевые сбои (DNS, таймаут, обрыв) — тоже отказ
     * шлюза, а не ошибка сервера. ConnectionException превращается в
     * PaymentGatewayException, и покупатель получает мягкий откат на
     * оплату по счёту вместо страницы 500.
     *
     * @param  array<string, mixed>  $body
     * @return array<string, mixed>
     */
    private function post(string $path, array $body): array
    {
        try {
            return $this->unwrap($this->request()->post($path, $body));
        } catch (ConnectionException $e) {
            throw new PaymentGatewayException("Uzum недоступен: {$e->getMessage()}");
        }
    }

    private function request(): PendingRequest
    {
        $proxy = trim((string) ($this->config['proxy'] ?? ''));

        return Http::baseUrl(rtrim((string) $this->config['base_url'], '/'))
            ->withHeaders([
                'X-Terminal-Id' => (string) $this->config['terminal_id'],
                'X-API-Key' => (string) $this->config['secret_key'],
                'Content-Language' => $this->contentLanguage(),
            ])
            ->acceptJson()
            ->connectTimeout(5)
            ->timeout(15)
            // Статический адрес для белого списка Uzum (см. config)
            ->when($proxy !== '', fn (PendingRequest $r) => $r->withOptions(['proxy' => $proxy]));
    }

    /** Язык платёжной формы — из локали покупателя; форма знает три. */
    private function contentLanguage(): string
    {
        return match (app()->getLocale()) {
            'uz' => 'uz-UZ',
            'en' => 'en-EN', // так в протоколе Uzum, не en-US
            default => 'ru-RU',
        };
    }

    /**
     * Ответ Uzum: HTTP 200 и errorCode 0, иначе исключение.
     *
     * @return array<string, mixed>
     */
    private function unwrap(HttpResponse $response): array
    {
        if (! $response->ok()) {
            throw new PaymentGatewayException("Uzum ответил HTTP {$response->status()}");
        }

        $body = $response->json();

        if (! is_array($body)) {
            throw new PaymentGatewayException('Uzum вернул не-JSON ответ');
        }

        $code = (int) ($body['errorCode'] ?? -1);

        if ($code !== 0) {
            $message = (string) ($body['message'] ?? 'без описания');

            throw new PaymentGatewayException("Uzum отказал: код {$code}, {$message}");
        }

        $result = $body['result'] ?? [];

        return is_array($result) ? $result : [];
    }

    /**
     * Ссылка платёжной страницы: сначала известные имена полей, затем
     * любая строка-адрес в result (в том числе во вложенных объектах) —
     * чтобы непредсказуемое имя поля не сорвало первый боевой платёж.
     *
     * @param  array<string, mixed>  $result
     */
    private function paymentPageUrl(array $result): ?string
    {
        foreach (self::PAY_URL_KEYS as $key) {
            $value = $result[$key] ?? null;

            if (is_string($value) && str_starts_with($value, 'http')) {
                return $value;
            }
        }

        foreach ($result as $value) {
            if (is_string($value) && str_starts_with($value, 'https://')) {
                return $value;
            }

            if (is_array($value) && ($nested = $this->paymentPageUrl($value)) !== null) {
                return $nested;
            }
        }

        return null;
    }

    /**
     * Убедиться, что нужные ключи заданы в окружении.
     *
     * @param  list<string>  $keys
     */
    private function require(array $keys): void
    {
        foreach ($keys as $key) {
            if (blank($this->config[$key] ?? null)) {
                throw new PaymentGatewayException("Uzum не настроен: не задан ключ «{$key}» (переменная окружения PAYMENTS_UZUM_".mb_strtoupper($key).')');
            }
        }
    }
}
