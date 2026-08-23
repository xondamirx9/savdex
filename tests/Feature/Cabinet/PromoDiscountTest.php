<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\Company;
use App\Models\Payment;
use App\Models\PaymentMethod;
use App\Models\PaymentTransaction;
use App\Models\Plan;
use App\Models\PromoCode;
use App\Models\Subscription;
use App\Models\User;
use App\Services\OrderService;
use App\Services\Payments\PaymentGateway;
use App\Services\Payments\PaymentGatewayManager;
use App\Support\CurrencyRate;
use Database\Seeders\PlanSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\Request;
use Illuminate\Testing\TestResponse;
use PHPUnit\Framework\Attributes\Test;
use Symfony\Component\HttpFoundation\Response;
use Tests\TestCase;

/**
 * Скидочный промокод: счёт на остаток цены и оплата онлайн.
 *
 * В отличие от кода на бесплатный период, скидочный код ничего не
 * дарит сразу: активация выставляет счёт на цену тарифа минус процент
 * и уводит покупателя на платёжную страницу. Тариф включается, когда
 * деньги дошли, — тем же путём, что и обычный оплаченный счёт.
 *
 * Цена ошибки — двойная скидка с одного кода или сожжённый код при
 * брошенной оплате, поэтому захват, повторный ввод и освобождение
 * кода при отмене счёта проверяются отдельно.
 */
class PromoDiscountTest extends TestCase
{
    use RefreshDatabase;

    public const PAY_URL = 'https://checkout.uzum.test/pay/discount42';

    private User $user;

    private Company $company;

    protected function setUp(): void
    {
        parent::setUp();

        $this->seed(PlanSeeder::class);

        $this->company = Company::factory()->create();
        $this->user = User::factory()->for($this->company)->create(['email_verified_at' => now()]);
    }

    private function premium(): Plan
    {
        return Plan::where('code', 'premium')->firstOrFail();
    }

    private function discountCode(int $percent = 30, array $overrides = []): PromoCode
    {
        return PromoCode::create(array_merge([
            'code' => PromoCode::generateCode(),
            'plan_id' => $this->premium()->id,
            'days' => 0,
            'discount_percent' => $percent,
            'is_active' => true,
        ], $overrides));
    }

    private function redeem(string $code): TestResponse
    {
        return $this->actingAs($this->user)->post('/cabinet/billing/promo', ['promo_code' => $code]);
    }

    /** Менеджер шлюзов с фальшивым шлюзом — как в CheckoutRedirectTest. */
    private function fakeGateway(): void
    {
        $gateway = new class implements PaymentGateway
        {
            public function provider(): string
            {
                return 'uzum';
            }

            public function createCheckout(Payment $payment, array $options = []): array
            {
                return ['redirect_url' => PromoDiscountTest::PAY_URL];
            }

            public function verifyCallback(Request $request): bool
            {
                return true;
            }

            public function parseCallback(Request $request): array
            {
                return ['status' => 'created', 'reference' => null, 'provider_transaction_id' => null, 'amount_minor' => null, 'raw' => []];
            }

            public function callbackResponse(bool $accepted, array $event): Response
            {
                return new Response;
            }

            public function chargeSavedCard(Payment $payment, PaymentMethod $card): array
            {
                return ['ok' => false, 'message' => ''];
            }

            public function refund(Payment $payment, int $amountMinor): array
            {
                return ['ok' => false, 'message' => ''];
            }
        };

        config(['payments.providers.uzum.checkout' => true]);

        $this->mock(PaymentGatewayManager::class, function ($mock) use ($gateway): void {
            $mock->shouldReceive('enabled')->andReturn(true);
            $mock->shouldReceive('default')->andReturn($gateway);
        });
    }

    // ── Активация ────────────────────────────────────────────

    #[Test]
    public function скидочный_код_выставляет_счёт_на_остаток_цены(): void
    {
        $promo = $this->discountCode(30);

        $this->redeem($promo->code)->assertRedirect()->assertSessionHasNoErrors();

        // Тариф сразу не выдаётся — сначала оплата
        $this->assertNull($this->company->fresh()->subscription);

        $payment = $this->company->payments()->where('status', 'pending')->first();
        $expected = OrderService::discounted($this->premium()->priceUzs(app(CurrencyRate::class)->usd()), 30);

        $this->assertNotNull($payment);
        $this->assertSame($expected, $payment->amount);
        $this->assertSame($promo->id, $payment->promo_code_id);
        $this->assertStringContainsString($promo->code, $payment->description);

        // Код захвачен при выставлении счёта: второй компании не достанется
        $promo->refresh();
        $this->assertNotNull($promo->used_at);
        $this->assertSame($this->company->id, $promo->used_by_company_id);
    }

    #[Test]
    public function при_включённой_кассе_код_уводит_на_платёжную_страницу(): void
    {
        $this->fakeGateway();

        $this->redeem($this->discountCode()->code)->assertRedirect(self::PAY_URL);

        // Провайдер записан: колбэк найдёт счёт и поймёт, чьим форматом его разбирать
        $this->assertSame('uzum', $this->company->payments()->where('status', 'pending')->first()->provider);
    }

    #[Test]
    public function оплата_счёта_со_скидкой_включает_тариф(): void
    {
        $promo = $this->discountCode();
        $this->redeem($promo->code);

        $payment = $this->company->payments()->where('status', 'pending')->firstOrFail();

        app(OrderService::class)->markPaid($payment, ['provider' => 'uzum', 'external_id' => 'UZ-100']);

        $subscription = $this->company->fresh()->subscription;

        $this->assertNotNull($subscription);
        $this->assertSame($this->premium()->id, $subscription->plan_id);
        $this->assertSame(Subscription::SOURCE_PAYMENT, $subscription->source);

        // Код связан с подпиской, которую помог купить
        $this->assertSame($subscription->id, $promo->fresh()->subscription_id);
    }

    /** Скидка — повод заплатить: оплата в прошлом коду не мешает. */
    #[Test]
    public function скидочный_код_доступен_платившей_компании(): void
    {
        Payment::create([
            'company_id' => $this->company->id,
            'number' => 'SVD-000777',
            'purpose' => 'subscription',
            'description' => 'Тариф',
            'amount' => 100000,
            'currency' => 'UZS',
            'provider' => 'invoice',
            'status' => 'paid',
            'paid_at' => now(),
        ]);

        $this->redeem($this->discountCode()->code)->assertSessionHasNoErrors();

        $this->assertNotNull($this->company->payments()->where('status', 'pending')->first());
    }

    // ── Повторный ввод и гонки ───────────────────────────────

    /** Ушёл с платёжной страницы и набрал код снова — тот же счёт, а не отказ. */
    #[Test]
    public function повторный_ввод_возвращает_к_тому_же_счёту(): void
    {
        $promo = $this->discountCode();

        $this->redeem($promo->code)->assertSessionHasNoErrors();
        $this->redeem($promo->code)->assertSessionHasNoErrors();

        $this->assertSame(1, $this->company->payments()->where('status', 'pending')->count());
    }

    #[Test]
    public function захваченный_код_второй_компании_не_достаётся(): void
    {
        $promo = $this->discountCode();
        $this->redeem($promo->code);

        $other = Company::factory()->create();
        $otherUser = User::factory()->for($other)->create(['email_verified_at' => now()]);

        $this->actingAs($otherUser)
            ->post('/cabinet/billing/promo', ['promo_code' => $promo->code])
            ->assertSessionHasErrors('promo_code');

        $this->assertSame(0, $other->payments()->count());
    }

    // ── Отмена счёта ─────────────────────────────────────────

    /** Брошенная оплата код не сжигает: отменённый счёт возвращает его в оборот. */
    #[Test]
    public function отмена_счёта_возвращает_код_в_оборот(): void
    {
        $promo = $this->discountCode();
        $this->redeem($promo->code);

        $payment = $this->company->payments()->where('status', 'pending')->firstOrFail();

        $this->actingAs($this->user)->post("/cabinet/billing/invoice/{$payment->id}/cancel");

        $promo->refresh();
        $this->assertNull($promo->used_at);
        $this->assertNull($promo->used_by_company_id);

        // Освобождённый код может активировать другая компания
        $other = Company::factory()->create();
        $otherUser = User::factory()->for($other)->create(['email_verified_at' => now()]);

        $this->actingAs($otherUser)
            ->post('/cabinet/billing/promo', ['promo_code' => $promo->code])
            ->assertSessionHasNoErrors();

        $this->assertNotNull($other->payments()->where('status', 'pending')->first());
    }

    /**
     * Отменить счёт можно и посреди карточной оплаты: Uzum уже завёл
     * транзакцию и в течение получаса может подтвердить списание по
     * отменённому счёту. Освобождённый в этот момент код успел бы дать
     * скидку второй компании — один код, две скидки.
     */
    #[Test]
    public function код_не_освобождается_пока_жива_карточная_транзакция(): void
    {
        $promo = $this->discountCode();
        $this->redeem($promo->code);

        $payment = $this->company->payments()->where('status', 'pending')->firstOrFail();

        PaymentTransaction::create([
            'payment_id' => $payment->id,
            'provider' => 'uzum',
            'provider_transaction_id' => 'UZ-LIVE-1',
            'state' => PaymentTransaction::STATE_CREATED,
            'amount_minor' => $payment->amountMinor(),
            'currency' => 'UZS',
        ]);

        $this->actingAs($this->user)->post("/cabinet/billing/invoice/{$payment->id}/cancel");

        // Счёт отменён, но код остаётся захваченным до исхода транзакции
        $this->assertSame('failed', $payment->fresh()->status);
        $this->assertNotNull($promo->fresh()->used_at);
    }

    /**
     * Поздний confirm по отменённому счёту не должен трогать код,
     * который уже освобождён и захвачен другой компанией.
     */
    #[Test]
    public function поздний_confirm_не_портит_чужой_код(): void
    {
        $promo = $this->discountCode();
        $this->redeem($promo->code);

        $abandoned = $this->company->payments()->where('status', 'pending')->firstOrFail();

        // Транзакций нет — отмена освобождает код
        $this->actingAs($this->user)->post("/cabinet/billing/invoice/{$abandoned->id}/cancel");
        $this->assertNull($promo->fresh()->used_at);

        // Код захватывает вторая компания
        $other = Company::factory()->create();
        $otherUser = User::factory()->for($other)->create(['email_verified_at' => now()]);
        $this->actingAs($otherUser)->post('/cabinet/billing/promo', ['promo_code' => $promo->code]);
        $this->assertSame($other->id, $promo->fresh()->used_by_company_id);

        // Поздний confirm провайдера закрывает отменённый счёт первой
        // компании — но чужой код при этом остаётся нетронутым
        app(OrderService::class)->markPaid($abandoned->fresh(), ['provider' => 'uzum', 'external_id' => 'UZ-LATE']);

        $promo->refresh();
        $this->assertSame($other->id, $promo->used_by_company_id);
        $this->assertNull($promo->subscription_id);
    }

    /** Два оплачиваемых счёта на один тариф — двойное списание при оплате обоих. */
    #[Test]
    public function скидочный_счёт_заменяет_полный_на_тот_же_тариф(): void
    {
        $this->actingAs($this->user)->post('/cabinet/billing/order', [
            'kind' => 'plan',
            'id' => $this->premium()->id,
        ]);

        $full = $this->company->payments()->where('status', 'pending')->firstOrFail();

        $this->redeem($this->discountCode()->code)->assertSessionHasNoErrors();

        // Полный счёт закрыт, оплачиваемым остался только скидочный
        $this->assertSame('failed', $full->fresh()->status);

        $pending = $this->company->payments()->where('status', 'pending')->get();
        $this->assertCount(1, $pending);
        $this->assertNotNull($pending->first()->promo_code_id);
    }

    /**
     * Код, оставшийся захваченным после отмены счёта (карточная оплата
     * была в полёте), не должен сгорать для владельца: повторный ввод
     * выставляет новый счёт и возвращает к оплате.
     */
    #[Test]
    public function владелец_захваченного_кода_может_продолжить_после_отмены(): void
    {
        $promo = $this->discountCode();
        $this->redeem($promo->code);

        $payment = $this->company->payments()->where('status', 'pending')->firstOrFail();

        PaymentTransaction::create([
            'payment_id' => $payment->id,
            'provider' => 'uzum',
            'provider_transaction_id' => 'UZ-LIVE-2',
            'state' => PaymentTransaction::STATE_CREATED,
            'amount_minor' => $payment->amountMinor(),
            'currency' => 'UZS',
        ]);

        $this->actingAs($this->user)->post("/cabinet/billing/invoice/{$payment->id}/cancel");

        // Код захвачен, открытых счетов нет — но владелец продолжает
        $this->redeem($promo->code)->assertSessionHasNoErrors();

        $reissued = $this->company->payments()->where('status', 'pending')->first();

        $this->assertNotNull($reissued);
        $this->assertSame($promo->id, $reissued->promo_code_id);
    }

    /**
     * Повторная отмена одного счёта (повтор вебхука провайдера) не
     * должна второй раз освобождать код, который компания уже успела
     * захватить под новый счёт.
     */
    #[Test]
    public function повторная_отмена_счёта_не_освобождает_код_второй_раз(): void
    {
        $promo = $this->discountCode();
        $this->redeem($promo->code);

        $first = $this->company->payments()->where('status', 'pending')->firstOrFail();

        app(OrderService::class)->cancel($first);
        $this->assertNull($promo->fresh()->used_at);

        // Код захвачен заново, под новый счёт
        $this->redeem($promo->code)->assertSessionHasNoErrors();
        $this->assertNotNull($promo->fresh()->used_at);

        // Повторная отмена первого счёта — уже no-op
        app(OrderService::class)->cancel($first->fresh());

        $this->assertNotNull($promo->fresh()->used_at);
        $this->assertSame(1, $this->company->payments()->where('status', 'pending')->count());
    }

    // ── Коды, выпущенные с ошибкой ───────────────────────────

    /** Скидка от нулевой цены — счёт на ноль сумов: такой код не работает. */
    #[Test]
    public function код_на_бесплатный_тариф_отклоняется(): void
    {
        $free = Plan::where('code', Plan::FREE)->firstOrFail();
        $promo = $this->discountCode(50, ['plan_id' => $free->id]);

        $this->redeem($promo->code)->assertSessionHasErrors('promo_code');

        // Отказ откатывает и захват: код не должен остаться погашенным
        $this->assertNull($promo->fresh()->used_at);
        $this->assertSame(0, $this->company->payments()->count());
    }

    #[Test]
    public function скидка_вне_диапазона_отклоняется(): void
    {
        $promo = $this->discountCode(0);

        $this->redeem($promo->code)->assertSessionHasErrors('promo_code');

        $this->assertNull($promo->fresh()->used_at);
    }
}
