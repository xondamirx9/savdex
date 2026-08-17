<?php

declare(strict_types=1);

namespace App\Services\Payments;

use App\Models\Payment;
use App\Models\PaymentMethod;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\JsonResponse;
use Symfony\Component\HttpFoundation\Response;

/**
 * Платёжный шлюз Uzum.
 *
 * Каркас готов, а провод (точные адреса, формат подписи и тел колбэков)
 * заполняется по документации мерчанта Uzum и проверяется на их
 * тестовом контуре. Пока боевой реализации нет, методы, которым нужен
 * протокол, честно бросают исключение — включать провайдера без них
 * нельзя (по умолчанию он и выключен).
 *
 * Что нужно из документации Uzum, чтобы дописать методы ниже:
 *   1. Базовые адреса теста и боя (base_url) и версия API.
 *   2. Схема аутентификации запросов (заголовок/подпись) и алгоритм
 *      подписи колбэка секретным ключом (что и в каком порядке хэшируется).
 *   3. Тело запроса «создать платёж/чек» и где в ответе ссылка оплаты.
 *   4. Формат и поля колбэка об оплате/отмене и какой ответ Uzum ждёт
 *      в подтверждение (код/тело).
 *   5. Привязка карты (binding) и списание по токену для автопродления.
 *   6. Единицы суммы (ожидаем тийины — Payment::amountMinor()).
 */
class UzumGateway implements PaymentGateway
{
    /** @param array<string, mixed> $config */
    public function __construct(private readonly array $config) {}

    public function provider(): string
    {
        return 'uzum';
    }

    public function createCheckout(Payment $payment, array $options = []): array
    {
        $this->require(['base_url', 'merchant_id', 'secret_key']);

        // TODO(uzum-docs §3): POST на {base_url} с суммой $payment->amountMinor(),
        // валютой config('payments.currency'), номером $payment->number и
        // return_url; из ответа вернуть ['redirect_url' => ...].
        throw new PaymentGatewayException('Uzum createCheckout ещё не реализован: нужна документация мерчанта Uzum');
    }

    /**
     * Merchant API Uzum не шлёт вебхуков на базовый адрес — весь диалог
     * (check, create, confirm, reverse, status) идёт на подпути и
     * обслуживается UzumMerchantController. Запрос на базу — чужой или
     * заблудившийся: не признаём, и WebhookController ответит отказом
     * в формате протокола, а не ошибкой сервера.
     */
    public function verifyCallback(Request $request): bool
    {
        return false;
    }

    public function parseCallback(Request $request): array
    {
        // TODO(uzum-docs §4): разобрать тело колбэка в нормализованное
        // событие: status (paid|failed|cancelled|pending), reference (наш
        // номер счёта), provider_transaction_id, amount_minor, raw.
        throw new PaymentGatewayException('Uzum parseCallback ещё не реализован: нужен формат колбэка Uzum');
    }

    public function callbackResponse(bool $accepted, array $event): Response
    {
        // 99999 — «сервис недоступен» из номенклатуры ошибок Uzum:
        // единственный честный ответ на запрос вне протокола
        return new JsonResponse([
            'status' => $accepted ? 'OK' : 'FAILED',
            'errorCode' => $accepted ? null : 99999,
        ], $accepted ? 200 : 400);
    }

    public function chargeSavedCard(Payment $payment, PaymentMethod $card): array
    {
        $this->require(['base_url', 'merchant_id', 'secret_key']);

        // TODO(uzum-docs §5): списание по токену привязанной карты
        // ($card->token) на сумму $payment->amountMinor() — для автопродления.
        throw new PaymentGatewayException('Uzum chargeSavedCard ещё не реализован: нужен протокол привязки/списания карты');
    }

    public function refund(Payment $payment, int $amountMinor): array
    {
        throw new PaymentGatewayException('Uzum refund ещё не реализован: нужен метод возврата из документации Uzum');
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
