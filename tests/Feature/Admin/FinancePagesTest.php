<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Pages\FinanceReports;
use App\Filament\Pages\GatewayReconciliation;
use App\Models\Company;
use App\Models\Payment;
use App\Models\PaymentTransaction;
use App\Models\Plan;
use App\Models\User;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Экраны финансовых отчётов и сверки.
 *
 * Рисуются с данными, а не пустыми: в этом проекте уже было, что
 * раздел открывался, пока в нём не появлялась первая строка — и падал
 * на ней. Пустой экран проверяет только маршрут.
 */
class FinancePagesTest extends TestCase
{
    use RefreshDatabase;

    private function admin(string $role): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => $role,
            'status' => 'active',
        ]);
    }

    private function plan(): Plan
    {
        return Plan::query()->firstOrCreate(['code' => 'business'], [
            'name' => 'Бизнес', 'price_usd' => 0, 'period_days' => 30,
        ]);
    }

    private function payment(string $status, int $amount = 100000, array $extra = []): Payment
    {
        return Payment::query()->create(array_merge([
            'company_id' => Company::factory()->create()->id,
            'number' => 'SD-'.fake()->unique()->numberBetween(1000, 9999),
            'purpose' => 'subscription',
            'description' => 'Тариф «Бизнес»',
            'plan_id' => $this->plan()->id,
            'amount' => $amount,
            'currency' => 'UZS',
            'provider' => 'uzum',
            'status' => $status,
            'paid_at' => $status === 'paid' ? now() : null,
        ], $extra));
    }

    // ── Доступ ──────────────────────────────────────────────────────

    /** По ТЗ финансы видят только суперадмин и финансист. */
    #[Test]
    public function отчёты_видны_суперадмину_и_финансисту(): void
    {
        foreach ([AdminAccess::SUPERADMIN, AdminAccess::FINANCE] as $role) {
            $this->actingAs($this->admin($role));

            $this->assertTrue(FinanceReports::canAccess(), "{$role} должен видеть отчёты");
            $this->assertTrue(GatewayReconciliation::canAccess(), "{$role} должен видеть сверку");
        }
    }

    /**
     * Администратор не видит финансы вовсе — ни сумм, ни отчётов.
     * Это решение из ТЗ, и ошибка здесь тихая: выручка утекает тому,
     * кому по роли не положена.
     */
    #[Test]
    public function остальные_роли_финансов_не_видят(): void
    {
        $closed = [
            AdminAccess::ADMIN, AdminAccess::SALES, AdminAccess::MODERATOR,
            AdminAccess::SUPPORT, AdminAccess::CONTENT_MANAGER,
            AdminAccess::SUPPLIER_MANAGER, AdminAccess::BUYER_MANAGER,
        ];

        foreach ($closed as $role) {
            $this->actingAs($this->admin($role));

            $this->assertFalse(FinanceReports::canAccess(), "{$role} не должен видеть отчёты");
            $this->assertFalse(GatewayReconciliation::canAccess(), "{$role} не должен видеть сверку");
        }
    }

    // ── Отрисовка ───────────────────────────────────────────────────

    #[Test]
    public function отчёты_рисуются_на_пустой_базе(): void
    {
        $this->actingAs($this->admin(AdminAccess::FINANCE));

        Livewire::test(FinanceReports::class)
            ->assertOk()
            ->assertSee('За выбранный период оплат не было');
    }

    #[Test]
    public function отчёты_рисуются_с_данными(): void
    {
        $this->actingAs($this->admin(AdminAccess::FINANCE));

        $this->payment('paid', 250000);
        $this->payment('paid', 120000, ['purpose' => 'credits']);

        Livewire::test(FinanceReports::class)
            ->assertOk()
            ->assertSee('370 000', escape: false)   // общая выручка
            ->assertSee('Бизнес')                    // разбивка по тарифам
            ->assertSee('Пакет контактов');          // разбивка по источникам
    }

    #[Test]
    public function сверка_на_исправных_данных_говорит_что_всё_сошлось(): void
    {
        $this->actingAs($this->admin(AdminAccess::FINANCE));

        $payment = $this->payment('paid');
        PaymentTransaction::query()->create([
            'payment_id' => $payment->id,
            'provider' => 'uzum',
            'provider_transaction_id' => fake()->uuid(),
            'state' => PaymentTransaction::STATE_PERFORMED,
            'amount_minor' => $payment->amountMinor(),
            'currency' => 'UZS',
            'payload' => [],
            'performed_at' => now(),
        ]);

        Livewire::test(GatewayReconciliation::class)
            ->assertOk()
            ->assertSee('Расхождений нет');
    }

    /** Самое важное на этом экране — чтобы расхождение было видно и названо. */
    #[Test]
    public function сверка_показывает_расхождение(): void
    {
        $this->actingAs($this->admin(AdminAccess::FINANCE));

        $payment = $this->payment('pending');
        PaymentTransaction::query()->create([
            'payment_id' => $payment->id,
            'provider' => 'uzum',
            'provider_transaction_id' => fake()->uuid(),
            'state' => PaymentTransaction::STATE_PERFORMED,
            'amount_minor' => $payment->amountMinor(),
            'currency' => 'UZS',
            'payload' => [],
            'performed_at' => now(),
        ]);

        Livewire::test(GatewayReconciliation::class)
            ->assertOk()
            ->assertSee('Деньги взяты, счёт не закрыт')
            ->assertSee($payment->number)
            ->assertDontSee('Расхождений нет');
    }

    /** Значок в меню зовёт, когда сверку неделями не открывают. */
    #[Test]
    public function значок_в_меню_считает_только_срочное(): void
    {
        $this->actingAs($this->admin(AdminAccess::FINANCE));

        // «Закрыт без транзакции» — предупреждение, а не срочное
        $this->payment('paid');
        $this->assertNull(GatewayReconciliation::getNavigationBadge());

        $unpaid = $this->payment('pending');
        PaymentTransaction::query()->create([
            'payment_id' => $unpaid->id,
            'provider' => 'uzum',
            'provider_transaction_id' => fake()->uuid(),
            'state' => PaymentTransaction::STATE_PERFORMED,
            'amount_minor' => $unpaid->amountMinor(),
            'currency' => 'UZS',
            'payload' => [],
            'performed_at' => now(),
        ]);

        $this->assertSame('1', GatewayReconciliation::getNavigationBadge());
    }

    /** Смена периода обязана менять то, что показано. */
    #[Test]
    public function период_переключается(): void
    {
        $this->actingAs($this->admin(AdminAccess::FINANCE));

        $this->payment('paid', 250000, ['paid_at' => now()->subMonth()->startOfMonth()->addDay()]);

        Livewire::test(FinanceReports::class)
            ->assertDontSee('250 000', escape: false)
            ->call('setPeriod', 'prev')
            ->assertSee('250 000', escape: false);
    }
}
