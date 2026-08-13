<?php

declare(strict_types=1);

namespace App\Services\Payments;

use App\Models\Payment;
use App\Models\PaymentMethod;
use Illuminate\Http\Request;
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

    public function verifyCallback(Request $request): bool
    {
        // TODO(uzum-docs §2): пересчитать подпись из тела колбэка и
        // webhook_secret, сравнить с присланной; при наличии — проверить IP
        // по config('payments.providers.uzum.callback_ips').
        throw new PaymentGatewayException('Uzum verifyCallback ещё не реализован: нужна схема подписи колбэка');
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
        // TODO(uzum-docs §4): вернуть ответ в формате, который ждёт Uzum
        // (код/тело подтверждения приёма колбэка).
        throw new PaymentGatewayException('Uzum callbackResponse ещё не реализован: нужен ожидаемый ответ на колбэк');
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
