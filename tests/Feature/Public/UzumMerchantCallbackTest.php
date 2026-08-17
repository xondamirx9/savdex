<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Company;
use App\Models\Payment;
use App\Models\PaymentTransaction;
use App\Models\Plan;
use App\Models\User;
use App\Services\OrderService;
use Database\Seeders\PlanSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Testing\TestResponse;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Merchant API Uzum: диалог check — create — confirm — reverse — status.
 *
 * По этому протоколу процессинг Uzum сам вызывает нашу сторону, и его
 * тестовый контур прогоняет ровно эти сценарии перед подключением:
 * счастливый путь, повторы каждого вызова (сетевые ретраи), неверные
 * суммы, чужие счета и просроченные транзакции.
 */
class UzumMerchantCallbackTest extends TestCase
{
    use RefreshDatabase;

    private const LOGIN = 'savdex-callback';

    private const PASSWORD = 'secret-callback-password';

    private const SERVICE_ID = '498624';

    private Company $company;

    private Payment $payment;

    protected function setUp(): void
    {
        parent::setUp();

        config([
            'payments.providers.uzum.enabled' => true,
            'payments.providers.uzum.callback_login' => self::LOGIN,
            'payments.providers.uzum.callback_password' => self::PASSWORD,
            'payments.providers.uzum.service_id' => self::SERVICE_ID,
        ]);

        $this->seed(PlanSeeder::class);

        $this->company = Company::factory()->create();
        $user = User::factory()->for($this->company)->create(['email_verified_at' => now()]);

        $plan = Plan::where('code', '!=', Plan::FREE)->where('is_active', true)->firstOrFail();
        $this->payment = app(OrderService::class)->orderPlan($this->company, $plan, $user);
    }

    /**
     * Вызов операции от имени Uzum: Basic auth и формат протокола.
     *
     * @param  array<string, mixed>  $body
     */
    private function uzum(string $operation, array $body = [], bool $authorized = true): TestResponse
    {
        $request = $authorized
            ? $this->withBasicAuth(self::LOGIN, self::PASSWORD)
            : $this;

        return $request->postJson("/payments/uzum/callback/{$operation}", [
            'serviceId' => self::SERVICE_ID,
            'timestamp' => now()->getTimestampMs(),
            ...$body,
        ]);
    }

    /** @return array<string, mixed> */
    private function createBody(string $transId = 'uz-tx-1'): array
    {
        return [
            'transId' => $transId,
            'amount' => $this->payment->amountMinor(),
            'params' => ['invoice' => $this->payment->number],
        ];
    }

    // ── Авторизация ──────────────────────────────────────────

    #[Test]
    public function без_basic_auth_отказ(): void
    {
        $this->uzum('check', ['params' => ['invoice' => $this->payment->number]], authorized: false)
            ->assertStatus(401)
            ->assertJson(['status' => 'FAILED', 'errorCode' => 10001]);
    }

    #[Test]
    public function с_неверным_паролем_отказ(): void
    {
        $this->withBasicAuth(self::LOGIN, 'wrong')
            ->postJson('/payments/uzum/callback/check', ['serviceId' => self::SERVICE_ID])
            ->assertStatus(401)
            ->assertJson(['errorCode' => 10001]);
    }

    /** Пустые логин и пароль в конфиге запирают эндпойнты, а не пускают всех. */
    #[Test]
    public function без_настроенных_реквизитов_заперто(): void
    {
        config([
            'payments.providers.uzum.callback_login' => null,
            'payments.providers.uzum.callback_password' => null,
        ]);

        $this->withBasicAuth('', '')
            ->postJson('/payments/uzum/callback/check', ['serviceId' => self::SERVICE_ID])
            ->assertStatus(401);
    }

    #[Test]
    public function чужой_service_id_отклоняется(): void
    {
        $this->withBasicAuth(self::LOGIN, self::PASSWORD)
            ->postJson('/payments/uzum/callback/check', ['serviceId' => '999'])
            ->assertStatus(400)
            ->assertJson(['errorCode' => 10006]);
    }

    #[Test]
    public function выключенный_провайдер_не_существует(): void
    {
        config(['payments.providers.uzum.enabled' => false]);

        $this->uzum('check')->assertNotFound();
    }

    #[Test]
    public function неизвестная_операция_отклоняется(): void
    {
        $this->uzum('foobar')->assertStatus(400)->assertJson(['errorCode' => 10003]);
    }

    // ── check ────────────────────────────────────────────────

    #[Test]
    public function check_находит_счёт_и_возвращает_сумму_в_тийинах(): void
    {
        $this->uzum('check', ['params' => ['invoice' => $this->payment->number]])
            ->assertOk()
            ->assertJson([
                'serviceId' => self::SERVICE_ID,
                'status' => 'OK',
                'data' => [
                    'invoice' => $this->payment->number,
                    'amount' => $this->payment->amount * 100,
                ],
            ]);
    }

    #[Test]
    public function check_незнакомого_счёта_отвечает_not_found(): void
    {
        $this->uzum('check', ['params' => ['invoice' => 'НЕТ-ТАКОГО']])
            ->assertStatus(400)
            ->assertJson(['errorCode' => 10007]);
    }

    #[Test]
    public function check_оплаченного_счёта_отвечает_already_paid(): void
    {
        app(OrderService::class)->markPaid($this->payment);

        $this->uzum('check', ['params' => ['invoice' => $this->payment->number]])
            ->assertStatus(400)
            ->assertJson(['errorCode' => 10008]);
    }

    #[Test]
    public function check_отменённого_счёта_отвечает_cancelled(): void
    {
        app(OrderService::class)->cancel($this->payment);

        $this->uzum('check', ['params' => ['invoice' => $this->payment->number]])
            ->assertStatus(400)
            ->assertJson(['errorCode' => 10009]);
    }

    // ── create ───────────────────────────────────────────────

    #[Test]
    public function create_заводит_транзакцию(): void
    {
        $this->uzum('create', $this->createBody())
            ->assertOk()
            ->assertJson(['status' => 'CREATED', 'transId' => 'uz-tx-1']);

        $this->assertDatabaseHas('payment_transactions', [
            'provider' => 'uzum',
            'provider_transaction_id' => 'uz-tx-1',
            'state' => PaymentTransaction::STATE_CREATED,
            'payment_id' => $this->payment->id,
        ]);
    }

    /** Сетевой повтор create не заводит вторую транзакцию. */
    #[Test]
    public function повторный_create_отвечает_already_created(): void
    {
        $this->uzum('create', $this->createBody());

        $this->uzum('create', $this->createBody())
            ->assertStatus(400)
            ->assertJson(['errorCode' => 10010]);

        $this->assertSame(1, PaymentTransaction::count());
    }

    #[Test]
    public function create_с_неверной_суммой_отклоняется(): void
    {
        $this->uzum('create', [...$this->createBody(), 'amount' => 100])
            ->assertStatus(400)
            ->assertJson(['errorCode' => 10011]);

        $this->assertSame(0, PaymentTransaction::count());
    }

    // ── confirm ──────────────────────────────────────────────

    #[Test]
    public function confirm_закрывает_счёт_и_начисляет_тариф(): void
    {
        $this->uzum('create', $this->createBody());

        $this->uzum('confirm', ['transId' => 'uz-tx-1'])
            ->assertOk()
            ->assertJson(['status' => 'CONFIRMED']);

        $this->payment->refresh();
        $this->assertSame('paid', $this->payment->status);
        $this->assertSame('uzum', $this->payment->provider);

        // Купленный тариф начислен компании — ради этого всё и затевалось
        $this->assertNotNull($this->company->fresh()->subscription);
    }

    /** Сетевой повтор confirm не начисляет тариф дважды. */
    #[Test]
    public function повторный_confirm_отвечает_already_confirmed(): void
    {
        $this->uzum('create', $this->createBody());
        $this->uzum('confirm', ['transId' => 'uz-tx-1']);

        $this->uzum('confirm', ['transId' => 'uz-tx-1'])
            ->assertStatus(400)
            ->assertJson(['errorCode' => 10016]);
    }

    #[Test]
    public function confirm_незнакомой_транзакции_отвечает_not_found(): void
    {
        $this->uzum('confirm', ['transId' => 'ghost'])
            ->assertStatus(400)
            ->assertJson(['errorCode' => 10014]);
    }

    /** Просроченная транзакция не подтверждается — деньги вернутся покупателю. */
    #[Test]
    public function confirm_просроченной_транзакции_отклоняется(): void
    {
        $this->uzum('create', $this->createBody());

        $this->travel(31)->minutes();

        $this->uzum('confirm', ['transId' => 'uz-tx-1'])
            ->assertStatus(400)
            ->assertJson(['errorCode' => 10015]);

        $this->assertSame('pending', $this->payment->fresh()->status);
    }

    /**
     * Счёт успели оплатить переводом, пока шла карточная оплата.
     * Второй раз не начисляем — Uzum вернёт деньги по своей транзакции.
     */
    #[Test]
    public function confirm_после_оплаты_переводом_отвечает_already_paid(): void
    {
        $this->uzum('create', $this->createBody());

        app(OrderService::class)->markPaid($this->payment);

        $this->uzum('confirm', ['transId' => 'uz-tx-1'])
            ->assertStatus(400)
            ->assertJson(['errorCode' => 10008]);
    }

    // ── reverse ──────────────────────────────────────────────

    /** Отменяется транзакция, а не счёт: его ещё можно оплатить иначе. */
    #[Test]
    public function reverse_отменяет_транзакцию_но_счёт_остаётся(): void
    {
        $this->uzum('create', $this->createBody());

        $this->uzum('reverse', ['transId' => 'uz-tx-1'])
            ->assertOk()
            ->assertJson(['status' => 'REVERSED']);

        $this->assertSame('pending', $this->payment->fresh()->status);
    }

    /** Подтверждённую не отменяем: тариф начислен, возврат — через поддержку. */
    #[Test]
    public function reverse_подтверждённой_отклоняется(): void
    {
        $this->uzum('create', $this->createBody());
        $this->uzum('confirm', ['transId' => 'uz-tx-1']);

        $this->uzum('reverse', ['transId' => 'uz-tx-1'])
            ->assertStatus(400)
            ->assertJson(['errorCode' => 10017]);

        $this->assertSame('paid', $this->payment->fresh()->status);
    }

    #[Test]
    public function повторный_reverse_отвечает_already_reversed(): void
    {
        $this->uzum('create', $this->createBody());
        $this->uzum('reverse', ['transId' => 'uz-tx-1']);

        $this->uzum('reverse', ['transId' => 'uz-tx-1'])
            ->assertStatus(400)
            ->assertJson(['errorCode' => 10018]);
    }

    // ── status ───────────────────────────────────────────────

    #[Test]
    public function status_показывает_подтверждённую_транзакцию(): void
    {
        $this->uzum('create', $this->createBody());
        $this->uzum('confirm', ['transId' => 'uz-tx-1']);

        $response = $this->uzum('status', ['transId' => 'uz-tx-1'])
            ->assertOk()
            ->assertJson(['status' => 'CONFIRMED']);

        $this->assertNotNull($response->json('confirmTime'));
        $this->assertNotNull($response->json('transTime'));
    }

    // ── База колбэка при включённом провайдере ───────────────

    /**
     * Запрос на базу без операции — вне протокола: отказ в формате
     * Uzum, а не ошибка сервера. До этого включённый провайдер
     * отвечал здесь пятисоткой.
     */
    #[Test]
    public function база_отвечает_отказом_а_не_ошибкой_сервера(): void
    {
        $this->postJson('/payments/uzum/callback', ['x' => 1])
            ->assertStatus(400)
            ->assertJson(['status' => 'FAILED', 'errorCode' => 99999]);
    }
}
