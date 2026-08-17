<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\Company;
use App\Models\Payment;
use App\Models\PaymentMethod;
use App\Models\Plan;
use App\Models\User;
use App\Services\Payments\PaymentGateway;
use App\Services\Payments\PaymentGatewayManager;
use Database\Seeders\PlanSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\Request;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Symfony\Component\HttpFoundation\Response;
use Tests\TestCase;

/**
 * Увод на платёжную страницу провайдера с кнопки покупки.
 *
 * Пока онлайн-касса выключена, кнопка выставляет счёт — этот путь
 * закрывает OrderFlowTest. Здесь проверяется второй режим: с включённым
 * провайдером покупатель уезжает на страницу оплаты, а при отказе
 * шлюза остаётся со счётом на руках, и покупка не теряется.
 */
class CheckoutRedirectTest extends TestCase
{
    use RefreshDatabase;

    /** Открытая, а не приватная: её читает анонимный класс-шлюз ниже. */
    public const PAY_URL = 'https://checkout.uzum.test/pay/abc123';

    private User $user;

    private Company $company;

    protected function setUp(): void
    {
        parent::setUp();

        $this->seed(PlanSeeder::class);

        $this->company = Company::factory()->create();
        $this->user = User::factory()->for($this->company)->create(['email_verified_at' => now()]);
    }

    private function paidPlan(): Plan
    {
        return Plan::where('code', '!=', Plan::FREE)->where('is_active', true)->firstOrFail();
    }

    /** Менеджер шлюзов, отдающий фальшивый шлюз с готовой ссылкой оплаты. */
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
                return ['redirect_url' => CheckoutRedirectTest::PAY_URL];
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

        $this->mock(PaymentGatewayManager::class, function ($mock) use ($gateway): void {
            $mock->shouldReceive('enabled')->andReturn(true);
            $mock->shouldReceive('default')->andReturn($gateway);
        });
    }

    // ── Касса включена ───────────────────────────────────────

    #[Test]
    public function покупка_уводит_на_платёжную_страницу(): void
    {
        $this->fakeGateway();

        $this->actingAs($this->user)
            ->post('/cabinet/billing/order', ['kind' => 'plan', 'id' => $this->paidPlan()->id])
            ->assertRedirect(self::PAY_URL);
    }

    /** Счёт создаётся и при онлайн-оплате: с него можно заплатить и переводом. */
    #[Test]
    public function счёт_при_этом_всё_равно_создаётся(): void
    {
        $this->fakeGateway();

        $this->actingAs($this->user)
            ->post('/cabinet/billing/order', ['kind' => 'plan', 'id' => $this->paidPlan()->id]);

        $payment = $this->company->payments()->where('status', 'pending')->first();

        $this->assertNotNull($payment);
        // Провайдер записан: колбэк найдёт счёт и поймёт, чьим форматом его разбирать
        $this->assertSame('uzum', $payment->provider);
    }

    /**
     * Интерфейс шлёт запросы через Inertia — внешний редирект для неё
     * особый: 409 с адресом в заголовке, по которому клиент делает
     * полный переход на чужую страницу.
     */
    #[Test]
    public function для_inertia_редирект_отдаётся_заголовком(): void
    {
        $this->fakeGateway();

        $this->actingAs($this->user)
            ->post('/cabinet/billing/order', ['kind' => 'plan', 'id' => $this->paidPlan()->id], ['X-Inertia' => 'true'])
            ->assertStatus(409)
            ->assertHeader('X-Inertia-Location', self::PAY_URL);
    }

    /** Повторное нажатие — «хочу оплатить», а не повод для второго счёта. */
    #[Test]
    public function повторная_покупка_уводит_на_оплату_существующего_счёта(): void
    {
        $this->fakeGateway();
        $plan = $this->paidPlan();

        $this->actingAs($this->user)->post('/cabinet/billing/order', ['kind' => 'plan', 'id' => $plan->id]);

        $this->actingAs($this->user)
            ->post('/cabinet/billing/order', ['kind' => 'plan', 'id' => $plan->id])
            ->assertRedirect(self::PAY_URL);

        $this->assertSame(1, $this->company->payments()->count());
    }

    #[Test]
    public function выставленный_счёт_оплачивается_кнопкой(): void
    {
        $this->fakeGateway();

        $this->actingAs($this->user)->post('/cabinet/billing/order', ['kind' => 'plan', 'id' => $this->paidPlan()->id]);
        $payment = $this->company->payments()->firstOrFail();

        $this->actingAs($this->user)
            ->post("/cabinet/billing/invoice/{$payment->id}/pay")
            ->assertRedirect(self::PAY_URL);
    }

    #[Test]
    public function чужой_счёт_оплатить_нельзя(): void
    {
        $this->fakeGateway();

        $strangerCompany = Company::factory()->create();
        $strangerUser = User::factory()->for($strangerCompany)->create(['email_verified_at' => now()]);
        $this->actingAs($strangerUser)->post('/cabinet/billing/order', ['kind' => 'plan', 'id' => $this->paidPlan()->id]);
        $stranger = $strangerCompany->payments()->firstOrFail();

        $this->actingAs($this->user)
            ->post("/cabinet/billing/invoice/{$stranger->id}/pay")
            ->assertNotFound();
    }

    #[Test]
    public function флаг_кассы_приходит_на_страницу(): void
    {
        $this->fakeGateway();

        $this->actingAs($this->user)
            ->get('/cabinet/billing')
            ->assertInertia(fn (AssertableInertia $page) => $page->where('checkout', true));
    }

    // ── Касса выключена или отказала ─────────────────────────

    #[Test]
    public function при_выключенной_кассе_флаг_выключен(): void
    {
        $this->actingAs($this->user)
            ->get('/cabinet/billing')
            ->assertInertia(fn (AssertableInertia $page) => $page->where('checkout', false));
    }

    /**
     * Провайдер включён, но шлюз не готов (нет ключей, недоступен).
     * Покупка не теряется: счёт выставлен, покупатель предупреждён
     * и может заплатить переводом. Сейчас это ровно состояние боевого
     * UzumGateway — протокол ещё не дописан.
     */
    #[Test]
    public function отказ_шлюза_оставляет_счёт_и_не_роняет_страницу(): void
    {
        config(['payments.providers.uzum.enabled' => true]);

        $this->actingAs($this->user)
            ->post('/cabinet/billing/order', ['kind' => 'plan', 'id' => $this->paidPlan()->id])
            ->assertRedirect()
            ->assertSessionHas('warning');

        $this->assertSame(1, $this->company->payments()->where('status', 'pending')->count());
    }

    #[Test]
    public function при_выключенной_кассе_кнопка_оплаты_счёта_не_работает_но_не_ломает(): void
    {
        $this->actingAs($this->user)->post('/cabinet/billing/order', ['kind' => 'plan', 'id' => $this->paidPlan()->id]);
        $payment = $this->company->payments()->firstOrFail();

        $this->actingAs($this->user)
            ->post("/cabinet/billing/invoice/{$payment->id}/pay")
            ->assertRedirect()
            ->assertSessionHas('warning');
    }
}
