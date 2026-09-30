<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Models\Company;
use App\Models\Payment;
use App\Models\PaymentTransaction;
use App\Models\Plan;
use App\Models\User;
use App\Support\AdminAccess;
use Filament\Facades\Filament;
use Filament\Navigation\NavigationItem;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Cache;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Пункты меню «Финансовые отчёты» и «Сверка со шлюзом».
 *
 * Сами экраны переехали в админку Django (этап 7, шаг 60): отрисовку с
 * данными проверяют python/tests/test_finance_reports.py и
 * test_gateway_reconciliation.py. Здесь — кому видны пункты и значок
 * срочного у сверки.
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

    /** @return array<string, NavigationItem> */
    private function items(): array
    {
        $panel = Filament::getPanel('admin');
        Filament::setCurrentPanel($panel);

        return collect($panel->getNavigation())
            ->flatMap(fn ($group) => $group->getItems())
            ->mapWithKeys(fn (NavigationItem $item): array => [(string) $item->getLabel() => $item])
            ->all();
    }

    private function badge(): ?string
    {
        return $this->items()['Сверка со шлюзом']->getBadge();
    }

    private function performed(Payment $payment, ?int $minor = null): void
    {
        PaymentTransaction::query()->create([
            'payment_id' => $payment->id,
            'provider' => 'uzum',
            'provider_transaction_id' => fake()->uuid(),
            'state' => PaymentTransaction::STATE_PERFORMED,
            'amount_minor' => $minor ?? $payment->amountMinor(),
            'currency' => 'UZS',
            'payload' => [],
            'performed_at' => now(),
        ]);
    }

    // ── Доступ ──────────────────────────────────────────────────────

    /** По ТЗ финансы видят только суперадмин и финансист. */
    #[Test]
    public function отчёты_видны_суперадмину_и_финансисту(): void
    {
        foreach ([AdminAccess::SUPERADMIN, AdminAccess::FINANCE] as $role) {
            $this->actingAs($this->admin($role));

            $items = $this->items();

            $this->assertSame('/admin/python?next=/py/admin/finance/payment/reports/',
                $items['Финансовые отчёты']->getUrl(), "{$role} должен видеть отчёты");
            $this->assertSame('/admin/python?next=/py/admin/finance/payment/reconciliation/',
                $items['Сверка со шлюзом']->getUrl(), "{$role} должен видеть сверку");
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

            $items = $this->items();

            $this->assertArrayNotHasKey('Финансовые отчёты', $items, "{$role} не должен видеть отчёты");
            $this->assertArrayNotHasKey('Сверка со шлюзом', $items, "{$role} не должен видеть сверку");
        }
    }

    // ── Значок сверки ───────────────────────────────────────────────

    /** Значок в меню зовёт, когда сверку неделями не открывают. */
    #[Test]
    public function значок_в_меню_считает_только_срочное(): void
    {
        $this->actingAs($this->admin(AdminAccess::FINANCE));

        // «Закрыт без транзакции» — предупреждение, а не срочное
        $this->payment('paid');
        Cache::forget('recon.urgent');
        $this->assertNull($this->badge());

        $this->performed($this->payment('pending'));

        Cache::forget('recon.urgent');
        $this->assertSame('1', $this->badge());
    }

    /** Значок берётся из кэша: он считается на каждой странице админки. */
    #[Test]
    public function значок_не_пересчитывается_на_каждой_странице(): void
    {
        $this->actingAs($this->admin(AdminAccess::FINANCE));

        $this->performed($this->payment('pending'));

        Cache::forget('recon.urgent');
        $this->assertSame('1', $this->badge());

        // Новое расхождение сразу после — значок держится на кэше
        $this->performed($this->payment('pending'));

        $this->assertSame('1', $this->badge(), 'значение обязано браться из кэша');

        Cache::forget('recon.urgent');
        $this->assertSame('2', $this->badge());
    }

    /** Расхождение сумм — срочное: в тийинах тоже. */
    #[Test]
    public function расхождение_в_копейках_зажигает_значок(): void
    {
        $this->actingAs($this->admin(AdminAccess::FINANCE));

        $this->performed($this->payment('paid', 100000), 10000050);

        Cache::forget('recon.urgent');
        $this->assertSame('1', $this->badge());
    }
}
