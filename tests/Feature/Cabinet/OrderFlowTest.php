<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Filament\Pages\Invoices;
use App\Models\Company;
use App\Models\CreditPack;
use App\Models\Payment;
use App\Models\Plan;
use App\Models\Setting;
use App\Models\Subscription;
use App\Models\User;
use App\Models\Wallet;
use App\Services\OrderService;
use Database\Seeders\PlanSeeder;
use Filament\Actions\Testing\TestAction;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Покупка тарифа и кредитов: счёт — оплата — начисление.
 *
 * До этого продукт продавал доступ, которого нельзя было купить:
 * таблица платежей существовала, но писать в неё было некому, тариф
 * назначался вручную из админки, кредиты начислялись оттуда же.
 */
class OrderFlowTest extends TestCase
{
    use RefreshDatabase;

    private User $user;

    private Company $company;

    private User $admin;

    protected function setUp(): void
    {
        parent::setUp();

        $this->seed(PlanSeeder::class);

        $this->company = Company::factory()->create();
        $this->user = User::factory()->for($this->company)->create(['email_verified_at' => now()]);

        $this->admin = User::factory()->create([
            'is_admin' => true,
            'admin_role' => User::ADMIN_SUPERADMIN,
            'status' => 'active',
        ]);
    }

    private function paidPlan(): Plan
    {
        return Plan::where('code', '!=', Plan::FREE)->where('is_active', true)->firstOrFail();
    }

    private function pack(): CreditPack
    {
        return CreditPack::where('is_active', true)->firstOrFail();
    }

    // ── Выставление счёта ────────────────────────────────────

    #[Test]
    public function заказ_тарифа_выставляет_счёт(): void
    {
        $plan = $this->paidPlan();

        $this->actingAs($this->user)
            ->post('/cabinet/billing/order', ['kind' => 'plan', 'id' => $plan->id])
            ->assertSessionHas('success');

        $payment = Payment::where('company_id', $this->company->id)->firstOrFail();

        $this->assertSame('pending', $payment->status);
        $this->assertSame('subscription', $payment->purpose);
        $this->assertSame($plan->id, $payment->plan_id);
        $this->assertGreaterThan(0, $payment->amount);
        $this->assertMatchesRegularExpression('/^SVD-\d{6}$/', $payment->number);
    }

    /** Счёт сам по себе ничего не открывает — доступ даёт оплата. */
    #[Test]
    public function счёт_не_выдаёт_тариф_до_оплаты(): void
    {
        $this->actingAs($this->user)
            ->post('/cabinet/billing/order', ['kind' => 'plan', 'id' => $this->paidPlan()->id]);

        $this->assertSame(Plan::FREE, $this->company->fresh()->plan()->code);
        $this->assertSame(0, Subscription::count());
    }

    #[Test]
    public function заказ_пакета_кредитов_выставляет_счёт(): void
    {
        $pack = $this->pack();

        $this->actingAs($this->user)
            ->post('/cabinet/billing/order', ['kind' => 'credits', 'id' => $pack->id])
            ->assertSessionHas('success');

        $payment = Payment::firstOrFail();

        $this->assertSame('credits', $payment->purpose);
        $this->assertSame($pack->id, $payment->credit_pack_id);
        $this->assertSame(0, $this->company->fresh()->wallet?->credits ?? 0, 'кредиты до оплаты не начисляются');
    }

    /**
     * Второй счёт на то же самое не выставляется: иначе за день
     * набирается десяток счетов на один тариф, и обе бухгалтерии
     * выясняют, какой из них оплачен.
     */
    #[Test]
    public function повторный_счёт_на_то_же_не_выставляется(): void
    {
        $plan = $this->paidPlan();

        $this->actingAs($this->user)->post('/cabinet/billing/order', ['kind' => 'plan', 'id' => $plan->id]);

        $this->actingAs($this->user)
            ->post('/cabinet/billing/order', ['kind' => 'plan', 'id' => $plan->id])
            ->assertSessionHas('warning');

        $this->assertSame(1, Payment::count());
    }

    #[Test]
    public function без_подтверждённой_почты_счёт_не_выставить(): void
    {
        $user = User::factory()->for($this->company)->create(['email_verified_at' => null]);

        $this->actingAs($user)
            ->post('/cabinet/billing/order', ['kind' => 'plan', 'id' => $this->paidPlan()->id])
            ->assertRedirect();

        $this->assertSame(0, Payment::count());
    }

    #[Test]
    public function покупатель_отменяет_свой_счёт(): void
    {
        $this->actingAs($this->user)->post('/cabinet/billing/order', ['kind' => 'plan', 'id' => $this->paidPlan()->id]);

        $payment = Payment::firstOrFail();

        $this->actingAs($this->user)
            ->post("/cabinet/billing/invoice/{$payment->id}/cancel")
            ->assertSessionHas('success');

        $this->assertSame('failed', $payment->fresh()->status);
    }

    /** Чужой счёт не отменить — и о его существовании не сообщаем. */
    #[Test]
    public function чужой_счёт_недоступен(): void
    {
        $stranger = Company::factory()->create();
        $payment = Payment::create([
            'company_id' => $stranger->id,
            'purpose' => 'credits',
            'description' => 'Пакет',
            'amount' => 100000,
            'status' => 'pending',
            'number' => 'SVD-000999',
        ]);

        $this->actingAs($this->user)
            ->post("/cabinet/billing/invoice/{$payment->id}/cancel")
            ->assertNotFound();

        $this->assertSame('pending', $payment->fresh()->status);
    }

    // ── Подтверждение оплаты ─────────────────────────────────

    #[Test]
    public function подтверждение_оплаты_активирует_тариф(): void
    {
        $plan = $this->paidPlan();

        $this->actingAs($this->user)->post('/cabinet/billing/order', ['kind' => 'plan', 'id' => $plan->id]);
        $payment = Payment::firstOrFail();

        $this->actingAs($this->admin);

        Livewire::test(Invoices::class)
            ->callAction(TestAction::make('confirm')->table($payment), ['note' => 'п/п 214 от 29.07']);

        $payment->refresh();

        $this->assertSame('paid', $payment->status);
        $this->assertNotNull($payment->paid_at);
        $this->assertSame($this->admin->id, $payment->confirmed_by);
        $this->assertNotNull($payment->subscription_id, 'подписка должна быть привязана к счёту');

        $this->assertSame($plan->code, $this->company->fresh()->plan()->code);
    }

    /** Оплаченная подписка помечается как оплаченная, а не как подарок. */
    #[Test]
    public function оплаченная_подписка_не_считается_ручной(): void
    {
        $this->actingAs($this->user)->post('/cabinet/billing/order', ['kind' => 'plan', 'id' => $this->paidPlan()->id]);

        app(OrderService::class)->confirm(Payment::firstOrFail(), $this->admin);

        $subscription = Subscription::firstOrFail();

        $this->assertSame(Subscription::SOURCE_PAYMENT, $subscription->source);
        $this->assertTrue($subscription->auto_renew);
    }

    #[Test]
    public function подтверждение_оплаты_начисляет_кредиты(): void
    {
        $pack = $this->pack();
        Wallet::create(['company_id' => $this->company->id, 'credits' => 2]);

        $this->actingAs($this->user)->post('/cabinet/billing/order', ['kind' => 'credits', 'id' => $pack->id]);

        app(OrderService::class)->confirm(Payment::firstOrFail(), $this->admin);

        $this->assertSame(2 + $pack->credits, $this->company->fresh()->wallet->credits);

        $this->assertDatabaseHas('wallet_transactions', [
            'company_id' => $this->company->id,
            'amount' => $pack->credits,
            'reason' => 'purchase',
        ]);
    }

    /** Повторное подтверждение не должно начислять второй раз. */
    #[Test]
    public function повторное_подтверждение_не_начисляет_дважды(): void
    {
        $pack = $this->pack();
        Wallet::create(['company_id' => $this->company->id, 'credits' => 0]);

        $this->actingAs($this->user)->post('/cabinet/billing/order', ['kind' => 'credits', 'id' => $pack->id]);
        $payment = Payment::firstOrFail();

        $orders = app(OrderService::class);
        $orders->confirm($payment, $this->admin);

        $second = $orders->confirm($payment->fresh(), $this->admin);

        $this->assertFalse($second['ok']);
        $this->assertSame($pack->credits, $this->company->fresh()->wallet->credits);
    }

    // ── Оплата провайдером (markPaid) ────────────────────────

    /**
     * Колбэк провайдера начисляет так же, как ручное подтверждение,
     * но без администратора — и помечает счёт провайдером.
     */
    #[Test]
    public function оплата_провайдером_начисляет_кредиты_без_админа(): void
    {
        $pack = $this->pack();
        Wallet::create(['company_id' => $this->company->id, 'credits' => 0]);

        $this->actingAs($this->user)->post('/cabinet/billing/order', ['kind' => 'credits', 'id' => $pack->id]);
        $payment = Payment::firstOrFail();

        $result = app(OrderService::class)->markPaid($payment, ['provider' => 'uzum', 'external_id' => 'UZ-777']);

        $this->assertTrue($result['ok']);
        $payment->refresh();
        $this->assertSame('paid', $payment->status);
        $this->assertSame('uzum', $payment->provider);
        $this->assertSame('UZ-777', $payment->external_id);
        $this->assertNull($payment->confirmed_by, 'у оплаты провайдером нет админа-подтвердившего');
        $this->assertSame($pack->credits, $this->company->fresh()->wallet->credits);
    }

    #[Test]
    public function оплата_провайдером_выдаёт_тариф(): void
    {
        $this->actingAs($this->user)->post('/cabinet/billing/order', ['kind' => 'plan', 'id' => $this->paidPlan()->id]);

        app(OrderService::class)->markPaid(Payment::firstOrFail(), ['provider' => 'uzum']);

        $subscription = Subscription::firstOrFail();
        $this->assertSame('active', $subscription->status);
        $this->assertSame(Subscription::SOURCE_PAYMENT, $subscription->source);
    }

    /** Повторный колбэк (провайдер шлёт их не по одному разу) не начисляет второй раз. */
    #[Test]
    public function повторный_колбэк_провайдера_не_начисляет_дважды(): void
    {
        $pack = $this->pack();
        Wallet::create(['company_id' => $this->company->id, 'credits' => 0]);

        $this->actingAs($this->user)->post('/cabinet/billing/order', ['kind' => 'credits', 'id' => $pack->id]);
        $payment = Payment::firstOrFail();

        $orders = app(OrderService::class);
        $orders->markPaid($payment, ['provider' => 'uzum', 'external_id' => 'UZ-777']);
        $second = $orders->markPaid($payment->fresh(), ['provider' => 'uzum', 'external_id' => 'UZ-777']);

        $this->assertFalse($second['ok']);
        $this->assertSame($pack->credits, $this->company->fresh()->wallet->credits);
    }

    #[Test]
    public function компания_узнаёт_о_зачислении(): void
    {
        $this->actingAs($this->user)->post('/cabinet/billing/order', ['kind' => 'credits', 'id' => $this->pack()->id]);

        app(OrderService::class)->confirm(Payment::firstOrFail(), $this->admin);

        $this->assertGreaterThanOrEqual(
            1,
            $this->user->alerts()->where('type', 'billing')->count(),
            'о зачислении должно приходить уведомление',
        );
    }

    // ── Кабинет ──────────────────────────────────────────────

    #[Test]
    public function кабинет_показывает_счета_и_предложения(): void
    {
        $this->actingAs($this->user)->post('/cabinet/billing/order', ['kind' => 'plan', 'id' => $this->paidPlan()->id]);

        $this->actingAs($this->user)
            ->get('/cabinet/billing')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->component('cabinet/Billing')
                ->has('invoices', 1)
                ->has('packs', 3)
                ->where('invoices.0.number', fn (string $n): bool => str_starts_with($n, 'SVD-')),
            );
    }

    /** Бесплатный тариф не покупают: счёт на ноль сумм — издевательство. */
    #[Test]
    public function бесплатный_тариф_не_предлагается_к_покупке(): void
    {
        $this->actingAs($this->user)
            ->get('/cabinet/billing')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('plans', fn ($plans): bool => collect($plans)
                    ->firstWhere('code', Plan::FREE)['orderable'] === false),
            );
    }

    #[Test]
    public function номер_счёта_читается_как_документ(): void
    {
        $this->assertSame('SVD-000001', OrderService::makeNumber(1));
        $this->assertSame('SVD-012345', OrderService::makeNumber(12345));
    }

    // ── Печатная форма счёта ─────────────────────────────────

    /**
     * Документ, который несут в банк.
     *
     * Отдельная страница вне Inertia: у платёжного документа свои поля
     * и своя печать, а не оформление сайта с шапкой и меню.
     */
    #[Test]
    public function счёт_открывается_печатной_формой(): void
    {
        $this->actingAs($this->user)->post('/cabinet/billing/order', ['kind' => 'plan', 'id' => $this->paidPlan()->id]);
        $payment = Payment::firstOrFail();

        $this->actingAs($this->user)
            ->get("/cabinet/billing/invoice/{$payment->id}")
            ->assertSuccessful()
            ->assertSee($payment->number)
            ->assertSee($payment->description)
            ->assertSee('Итого к оплате')
            // Назначение платежа с номером — то, без чего оплату ищут руками
            ->assertSee('В назначении платежа укажите номер счёта', false);
    }

    /**
     * Получатель в счёте — полное наименование как в банковских
     * документах: платёж по счёту, где получатель назван короче, чем
     * в договоре с банком, банк отклоняет.
     */
    #[Test]
    public function счёт_показывает_реквизиты_площадки(): void
    {
        Setting::updateOrCreate(['key' => 'legal_full_name'], ['group' => 'legal', 'label' => 'Полное наименование', 'type' => 'string', 'value' => '"SAVDEX" MCHJ']);
        Setting::updateOrCreate(['key' => 'legal_account'], ['group' => 'legal', 'label' => 'Счёт', 'type' => 'string', 'value' => '2020 8000 1234 5678 9001']);

        $this->actingAs($this->user)->post('/cabinet/billing/order', ['kind' => 'credits', 'id' => $this->pack()->id]);

        $this->actingAs($this->user)
            ->get('/cabinet/billing/invoice/'.Payment::firstOrFail()->id)
            // Без false: кавычки в наименовании уходят в HTML экранированными
            ->assertSee('"SAVDEX" MCHJ')
            ->assertSee('2020 8000 1234 5678 9001');
    }

    /** Пока полное наименование не заполнено, в счёте краткое — без пустой строки. */
    #[Test]
    public function счёт_обходится_кратким_наименованием(): void
    {
        Setting::updateOrCreate(['key' => 'legal_full_name'], ['group' => 'legal', 'label' => 'Полное наименование', 'type' => 'string', 'value' => '']);
        Setting::updateOrCreate(['key' => 'legal_name'], ['group' => 'legal', 'label' => 'Юрлицо', 'type' => 'string', 'value' => 'ООО «SAVDEX»']);

        $this->actingAs($this->user)->post('/cabinet/billing/order', ['kind' => 'credits', 'id' => $this->pack()->id]);

        $this->actingAs($this->user)
            ->get('/cabinet/billing/invoice/'.Payment::firstOrFail()->id)
            ->assertSee('ООО «SAVDEX»', false);
    }

    /** Чужой счёт недоступен — и о его существовании не сообщаем. */
    #[Test]
    public function чужой_счёт_не_распечатать(): void
    {
        $payment = Payment::create([
            'company_id' => Company::factory()->create()->id,
            'purpose' => 'credits',
            'description' => 'Пакет',
            'amount' => 100000,
            'status' => 'pending',
            'number' => 'SVD-000777',
        ]);

        $this->actingAs($this->user)
            ->get("/cabinet/billing/invoice/{$payment->id}")
            ->assertNotFound();
    }
}
