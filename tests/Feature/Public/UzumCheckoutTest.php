<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Company;
use App\Models\Payment;
use App\Models\PaymentTransaction;
use App\Models\Plan;
use App\Models\User;
use App\Services\OrderService;
use App\Services\Payments\PaymentGatewayException;
use App\Services\Payments\PaymentGatewayManager;
use Database\Seeders\PlanSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\Client\ConnectionException;
use Illuminate\Http\Client\Request as ClientRequest;
use Illuminate\Support\Facades\Http;
use Illuminate\Testing\TestResponse;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Uzum Checkout: регистрация платежа и колбэк об оплате.
 *
 * Исходящая сторона (/payment/register, /payment/getOrderStatus)
 * подменяется Http::fake — проверяются заголовки X-Terminal-Id и
 * X-API-Key, тело запроса и разбор ответа. Входящая — реальный POST
 * на /payments/uzum/callback, как его шлёт Uzum.
 *
 * Ключевой инвариант: колбэк не подписан, поэтому начисление происходит
 * только после того, как getOrderStatus сам подтвердил COMPLETED, а счёт
 * ищется по orderId нашей же регистрации (external_id), не по номеру
 * счёта из тела колбэка.
 */
class UzumCheckoutTest extends TestCase
{
    use RefreshDatabase;

    private const BASE_URL = 'https://checkout.uzum.test';

    private const TERMINAL = 'f2b7a2f4-1111-2222-3333-444455556666';

    private const API_KEY = 'test-api-key';

    private const ORDER_ID = 'b3e1eced-f2bd-4d8c-9765-fbc9d1d222d5';

    private const PAY_URL = 'https://checkout.uzum.test/form/'.self::ORDER_ID;

    private Company $company;

    private Payment $payment;

    protected function setUp(): void
    {
        parent::setUp();

        config([
            'payments.providers.uzum.enabled' => true,
            'payments.providers.uzum.checkout' => true,
            'payments.providers.uzum.base_url' => self::BASE_URL,
            'payments.providers.uzum.terminal_id' => self::TERMINAL,
            'payments.providers.uzum.secret_key' => self::API_KEY,
            'payments.providers.uzum.return_url' => 'https://savdex.test/cabinet/billing',
        ]);

        $this->seed(PlanSeeder::class);

        $this->company = Company::factory()->create();
        $user = User::factory()->for($this->company)->create(['email_verified_at' => now()]);

        $plan = Plan::where('code', '!=', Plan::FREE)->where('is_active', true)->firstOrFail();
        $this->payment = app(OrderService::class)->orderPlan($this->company, $plan, $user);
    }

    // ── Регистрация платежа ──────────────────────────────────

    #[Test]
    public function register_sends_credentials_and_returns_payment_page(): void
    {
        Http::fake([
            self::BASE_URL.'/api/v1/payment/register' => Http::response([
                'errorCode' => 0,
                'message' => 'ok',
                'result' => ['orderId' => self::ORDER_ID, 'paymentRedirectUrl' => self::PAY_URL],
            ]),
        ]);

        $result = app(PaymentGatewayManager::class)->for('uzum')->createCheckout($this->payment);

        $this->assertSame(self::PAY_URL, $result['redirect_url']);
        $this->assertSame(self::ORDER_ID, $result['order_id']);
        // orderId запомнен: по нему колбэк найдёт счёт
        $this->assertSame(self::ORDER_ID, $this->payment->refresh()->external_id);

        Http::assertSent(function (ClientRequest $request): bool {
            return $request->hasHeader('X-Terminal-Id', self::TERMINAL)
                && $request->hasHeader('X-API-Key', self::API_KEY)
                && $request['amount'] === $this->payment->amountMinor()
                && $request['currency'] === 860
                && $request['orderNumber'] === $this->payment->number
                && $request['viewType'] === 'REDIRECT'
                && $request['paymentParams']['payType'] === 'ONE_STEP';
        });
    }

    #[Test]
    public function register_error_code_becomes_exception(): void
    {
        Http::fake([
            self::BASE_URL.'/api/v1/payment/register' => Http::response([
                'errorCode' => 3001,
                'message' => 'Терминал не найден',
            ]),
        ]);

        $this->expectException(PaymentGatewayException::class);
        $this->expectExceptionMessage('3001');

        app(PaymentGatewayManager::class)->for('uzum')->createCheckout($this->payment);
    }

    #[Test]
    public function register_without_pay_url_is_rejected(): void
    {
        Http::fake([
            self::BASE_URL.'/api/v1/payment/register' => Http::response([
                'errorCode' => 0,
                'result' => ['orderId' => self::ORDER_ID],
            ]),
        ]);

        $this->expectException(PaymentGatewayException::class);

        app(PaymentGatewayManager::class)->for('uzum')->createCheckout($this->payment);
    }

    // ── Колбэк об оплате ─────────────────────────────────────

    #[Test]
    public function confirmed_success_callback_marks_payment_paid(): void
    {
        $this->registerOrder();
        $this->fakeOrderStatus('COMPLETED');

        $this->deliverCallback(['operationState' => 'SUCCESS'])->assertOk();

        $this->assertSame('paid', $this->payment->refresh()->status);
        $tx = PaymentTransaction::where('provider_transaction_id', self::ORDER_ID)->firstOrFail();
        $this->assertSame(PaymentTransaction::STATE_PERFORMED, $tx->state);
    }

    #[Test]
    public function success_callback_is_idempotent_on_redelivery(): void
    {
        $this->registerOrder();
        $this->fakeOrderStatus('COMPLETED');

        $this->deliverCallback(['operationState' => 'SUCCESS'])->assertOk();
        $this->deliverCallback(['operationState' => 'SUCCESS'])->assertOk();

        $this->assertSame('paid', $this->payment->refresh()->status);
        $this->assertSame(1, PaymentTransaction::where('provider_transaction_id', self::ORDER_ID)->count());
    }

    #[Test]
    public function unconfirmed_success_callback_is_rejected_for_retry(): void
    {
        $this->registerOrder();
        // Uzum говорит SUCCESS, но статус заказа — ещё не COMPLETED:
        // начислять нельзя, 400 заставит Uzum повторить колбэк
        $this->fakeOrderStatus('REGISTERED');

        $this->deliverCallback(['operationState' => 'SUCCESS'])->assertStatus(400);

        $this->assertSame('pending', $this->payment->refresh()->status);
    }

    #[Test]
    public function failed_attempt_keeps_invoice_payable(): void
    {
        $this->registerOrder();

        // Неуспех карточной попытки — не отмена счёта: его всё ещё
        // можно оплатить другой картой или переводом
        $this->deliverCallback(['operationState' => 'FAIL'])->assertOk();

        $this->assertSame('pending', $this->payment->refresh()->status);
    }

    #[Test]
    public function callback_with_unknown_order_is_rejected(): void
    {
        $this->fakeOrderStatus('COMPLETED');

        $this->deliverCallback(['orderId' => 'never-registered', 'operationState' => 'SUCCESS'])
            ->assertStatus(400);
    }

    #[Test]
    public function callback_cannot_redirect_payout_to_another_invoice(): void
    {
        // Атака: чужой orderNumber в теле при оплаченном заказе другого
        // счёта. Счёт ищется по orderId регистрации, а не по номеру из
        // колбэка — второй счёт остаётся неоплаченным
        $this->registerOrder();
        $this->fakeOrderStatus('COMPLETED');

        $other = app(OrderService::class)->orderPlan(
            $this->company,
            Plan::where('code', '!=', Plan::FREE)->where('is_active', true)->firstOrFail(),
            User::factory()->for($this->company)->create(['email_verified_at' => now()]),
        );

        $this->deliverCallback(['operationState' => 'SUCCESS', 'orderNumber' => $other->number])->assertOk();

        $this->assertSame('paid', $this->payment->refresh()->status);
        $this->assertSame('pending', $other->refresh()->status);
    }

    #[Test]
    public function garbage_callback_is_rejected(): void
    {
        $this->postJson('/payments/uzum/callback', ['hello' => 'world'])->assertStatus(400);
    }

    #[Test]
    public function callback_is_locked_when_provider_disabled(): void
    {
        config(['payments.providers.uzum.enabled' => false]);

        $this->deliverCallback(['operationState' => 'SUCCESS'])->assertNotFound();
    }

    // ── Недоступность Uzum ───────────────────────────────────

    #[Test]
    public function network_failure_becomes_gateway_exception(): void
    {
        Http::fake(fn () => throw new ConnectionException('cURL error 6: Could not resolve host'));

        $this->expectException(PaymentGatewayException::class);
        $this->expectExceptionMessage('недоступен');

        app(PaymentGatewayManager::class)->for('uzum')->createCheckout($this->payment);
    }

    #[Test]
    public function buy_button_survives_gateway_outage(): void
    {
        // Uzum лежит или не резолвится — покупатель получает мягкий
        // откат на оплату по счёту, а не страницу 500
        Http::fake(fn () => throw new ConnectionException('cURL error 28: Connection timed out'));

        $user = User::factory()->for($this->company)->create(['email_verified_at' => now()]);
        $plan = Plan::where('code', '!=', Plan::FREE)->where('is_active', true)->firstOrFail();

        $this->actingAs($user)
            ->from('/cabinet/billing')
            ->post('/cabinet/billing/order', ['kind' => 'plan', 'id' => $plan->id])
            ->assertRedirect('/cabinet/billing')
            ->assertSessionHas('warning');

        // Счёт при этом остаётся оплачиваемым переводом
        $this->assertSame('pending', $this->payment->refresh()->status);
    }

    // ── Общее ────────────────────────────────────────────────

    /** Счёт зарегистрирован в Checkout: orderId сохранён как external_id. */
    private function registerOrder(): void
    {
        $this->payment->fill(['provider' => 'uzum', 'external_id' => self::ORDER_ID])->save();
    }

    private function fakeOrderStatus(string $status): void
    {
        Http::fake([
            self::BASE_URL.'/api/v1/payment/getOrderStatus' => Http::response([
                'errorCode' => 0,
                'result' => ['orderId' => self::ORDER_ID, 'status' => $status],
            ]),
        ]);
    }

    /** @param array<string, mixed> $body */
    private function deliverCallback(array $body): TestResponse
    {
        return $this->postJson('/payments/uzum/callback', [
            'orderId' => self::ORDER_ID,
            'operationType' => 'AUTHORIZE',
            'orderNumber' => $this->payment->number,
            ...$body,
        ]);
    }
}
