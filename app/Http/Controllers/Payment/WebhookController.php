<?php

declare(strict_types=1);

namespace App\Http\Controllers\Payment;

use App\Http\Controllers\Controller;
use App\Models\Payment;
use App\Models\PaymentTransaction;
use App\Services\OrderService;
use App\Services\Payments\PaymentGatewayException;
use App\Services\Payments\PaymentGatewayManager;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Log;
use Symfony\Component\HttpFoundation\Response;

/**
 * Приём колбэков платёжных провайдеров.
 *
 * Маршрут публичный (провайдер стучится снаружи, без нашей сессии) и
 * потому вынесен из CSRF и авторизации. Защита — на уровне провайдера:
 * подпись колбэка проверяется в шлюзе до всякого начисления.
 *
 * Начисление идёт через OrderService::markPaid — тот же путь, что и
 * ручное подтверждение. Колбэк приходит асинхронно и может повториться,
 * поэтому и ledger (payment_transactions), и markPaid идемпотентны:
 * повторный колбэк с тем же id транзакции не начислит тариф дважды.
 */
class WebhookController extends Controller
{
    public function __construct(
        private readonly PaymentGatewayManager $gateways,
        private readonly OrderService $orders,
    ) {}

    public function handle(Request $request, string $provider): Response
    {
        // Неизвестный или выключенный провайдер — как будто маршрута нет
        if (! $this->gateways->enabled($provider)) {
            abort(404);
        }

        $gateway = $this->gateways->for($provider);

        try {
            if (! $gateway->verifyCallback($request)) {
                Log::warning('payment.callback.bad_signature', ['provider' => $provider]);

                return $gateway->callbackResponse(false, $this->emptyEvent());
            }

            $event = $gateway->parseCallback($request);
            $payment = $this->resolvePayment($event['reference'] ?? null);

            if ($payment === null) {
                Log::warning('payment.callback.unknown_invoice', ['provider' => $provider, 'reference' => $event['reference'] ?? null]);

                return $gateway->callbackResponse(false, $event);
            }

            $this->apply($provider, $payment, $event);

            return $gateway->callbackResponse(true, $event);
        } catch (PaymentGatewayException $e) {
            Log::error('payment.callback.gateway_error', ['provider' => $provider, 'message' => $e->getMessage()]);

            return $gateway->callbackResponse(false, $this->emptyEvent());
        }
    }

    /**
     * Записать транзакцию и, если оплата, начислить купленное.
     *
     * @param  array{status: string, reference: string|null, provider_transaction_id: string|null, amount_minor: int|null, raw: array<string, mixed>}  $event
     */
    private function apply(string $provider, Payment $payment, array $event): void
    {
        $txId = $event['provider_transaction_id'] ?? null;

        // Идемпотентность: уже проведённую транзакцию второй раз не проводим
        $tx = $txId !== null
            ? PaymentTransaction::firstOrNew(['provider' => $provider, 'provider_transaction_id' => $txId])
            : new PaymentTransaction(['provider' => $provider]);

        if ($tx->exists && $tx->state === PaymentTransaction::STATE_PERFORMED) {
            return;
        }

        $tx->fill([
            'payment_id' => $payment->id,
            'amount_minor' => $event['amount_minor'] ?? null,
            'currency' => (string) config('payments.currency', 'UZS'),
            'payload' => $event['raw'] ?? [],
        ]);

        match ($event['status']) {
            'paid' => $this->settlePaid($payment, $provider, $txId, $tx),
            'cancelled', 'failed' => $this->settleCancelled($payment, $tx),
            default => $tx->fill(['state' => PaymentTransaction::STATE_CREATED])->save(),
        };
    }

    private function settlePaid(Payment $payment, string $provider, ?string $txId, PaymentTransaction $tx): void
    {
        $this->orders->markPaid($payment, array_filter([
            'provider' => $provider,
            'external_id' => $txId,
        ], fn ($v): bool => $v !== null));

        $tx->fill(['state' => PaymentTransaction::STATE_PERFORMED, 'performed_at' => now()])->save();
    }

    private function settleCancelled(Payment $payment, PaymentTransaction $tx): void
    {
        $this->orders->cancel($payment, null, 'Отмена на стороне провайдера');
        $tx->fill(['state' => PaymentTransaction::STATE_CANCELLED, 'cancelled_at' => now()])->save();
    }

    private function resolvePayment(?string $reference): ?Payment
    {
        if ($reference === null || $reference === '') {
            return null;
        }

        return Payment::query()
            ->where('number', $reference)
            ->orWhere('external_id', $reference)
            ->first();
    }

    /** @return array{status: string, reference: null, provider_transaction_id: null, amount_minor: null, raw: array<string, mixed>} */
    private function emptyEvent(): array
    {
        return ['status' => 'failed', 'reference' => null, 'provider_transaction_id' => null, 'amount_minor' => null, 'raw' => []];
    }
}
