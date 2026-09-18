<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Models\Company;
use App\Models\Payment;
use App\Models\Plan;
use App\Models\Refund;
use App\Models\Subscription;
use App\Support\FinanceReport;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Carbon;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Финансовые отчёты.
 *
 * Проверяются не столько суммы, сколько определения: «отток 12%» без
 * уточнения, что именно считали, не значит ничего, и цена ошибки здесь —
 * решение, принятое по неверной цифре.
 */
class FinanceReportTest extends TestCase
{
    use RefreshDatabase;

    private function paid(int $amount, ?Carbon $at = null, array $extra = []): Payment
    {
        return Payment::query()->create(array_merge([
            'company_id' => Company::factory()->create()->id,
            'number' => 'SD-'.fake()->unique()->numberBetween(1000, 9999),
            'purpose' => 'subscription',
            'description' => 'Тариф',
            'amount' => $amount,
            'currency' => 'UZS',
            'provider' => 'uzum',
            'status' => 'paid',
            'paid_at' => $at ?? now(),
        ], $extra));
    }

    private function period(): array
    {
        return [now()->startOfMonth(), now()->endOfMonth()];
    }

    /** RefreshDatabase сидеры не гоняет — тариф заводится тестом. */
    private function plan(string $code = 'business', string $name = 'Бизнес'): Plan
    {
        return Plan::query()->firstOrCreate(['code' => $code], [
            'name' => $name,
            'price_usd' => 0,
            'period_days' => 30,
        ]);
    }

    // ── Выручка ─────────────────────────────────────────────────────

    #[Test]
    public function выручка_считает_только_оплаченное(): void
    {
        $this->paid(100000);
        $this->paid(50000);
        $this->paid(999999, null, ['status' => 'pending', 'paid_at' => null]);
        $this->paid(888888, null, ['status' => 'failed', 'paid_at' => null]);

        [$from, $to] = $this->period();
        $revenue = FinanceReport::revenue($from, $to);

        $this->assertSame(150000, $revenue['UZS']['gross']);
        $this->assertSame(2, $revenue['UZS']['count']);
    }

    /** Возврат уменьшает выручку по дате возврата, а не по дате платежа. */
    #[Test]
    public function возврат_вычитается_из_выручки(): void
    {
        $payment = $this->paid(100000);

        Refund::query()->create([
            'payment_id' => $payment->id,
            'company_id' => $payment->company_id,
            'amount' => 30000,
            'currency' => 'UZS',
            'reason' => 'Клиент передумал',
            'status' => Refund::STATUS_DONE,
            'decided_at' => now(),
        ]);

        [$from, $to] = $this->period();
        $revenue = FinanceReport::revenue($from, $to);

        $this->assertSame(100000, $revenue['UZS']['gross']);
        $this->assertSame(30000, $revenue['UZS']['refunded']);
        $this->assertSame(70000, $revenue['UZS']['net']);
    }

    /** Заявленный возврат ещё не деньги: вычитается только проведённый. */
    #[Test]
    public function незавершённый_возврат_не_вычитается(): void
    {
        $payment = $this->paid(100000);

        Refund::query()->create([
            'payment_id' => $payment->id,
            'company_id' => $payment->company_id,
            'amount' => 30000,
            'currency' => 'UZS',
            'reason' => 'Разбираемся',
            'status' => Refund::STATUS_REQUESTED,
        ]);

        [$from, $to] = $this->period();

        $this->assertSame(100000, FinanceReport::revenue($from, $to)['UZS']['net']);
    }

    /**
     * Сумма сумов и долларов — не деньги, а число. Пока все платежи
     * в UZS, но столбец в базе есть, и отчёт обязан пережить вторую
     * валюту, а не посчитать её как первую.
     */
    #[Test]
    public function валюты_не_складываются(): void
    {
        $this->paid(100000);
        $this->paid(50, null, ['currency' => 'USD']);

        [$from, $to] = $this->period();
        $revenue = FinanceReport::revenue($from, $to);

        $this->assertSame(100000, $revenue['UZS']['gross']);
        $this->assertSame(50, $revenue['USD']['gross']);
    }

    // ── По месяцам ──────────────────────────────────────────────────

    /** Месяц без единой продажи — это факт, а не отсутствие строки. */
    #[Test]
    public function пустые_месяцы_остаются_в_отчёте(): void
    {
        $this->paid(100000, now()->startOfMonth());

        $rows = FinanceReport::byMonth(now()->subMonths(2)->startOfMonth(), now()->endOfMonth());

        $this->assertCount(3, $rows);
        $this->assertSame(0, $rows[0]['gross']);
        $this->assertSame(0, $rows[1]['gross']);
        $this->assertSame(100000, $rows[2]['gross']);
    }

    // ── По тарифам и источникам ─────────────────────────────────────

    #[Test]
    public function выручка_раскладывается_по_тарифам(): void
    {
        $business = $this->plan();

        $this->paid(300000, null, ['plan_id' => $business->id]);
        $this->paid(100000);

        [$from, $to] = $this->period();
        $rows = FinanceReport::byPlan($from, $to);

        $this->assertSame($business->name, $rows[0]['name'], 'крупнейший тариф должен быть первым');
        $this->assertSame(300000, $rows[0]['gross']);
        $this->assertSame('Без тарифа', $rows[1]['name']);
    }

    #[Test]
    public function выручка_раскладывается_по_источникам(): void
    {
        $this->paid(300000, null, ['purpose' => 'subscription']);
        $this->paid(100000, null, ['purpose' => 'credits']);

        [$from, $to] = $this->period();
        $rows = FinanceReport::bySource($from, $to);

        $this->assertSame('Подписка', $rows[0]['purpose']);
        $this->assertSame('uzum', $rows[0]['provider']);
        $this->assertSame('Пакет контактов', $rows[1]['purpose']);
    }

    // ── Продления и отток ───────────────────────────────────────────

    private function subscription(Company $company, array $attrs): Subscription
    {
        return Subscription::query()->create(array_merge([
            'company_id' => $company->id,
            'plan_id' => $this->plan()->id,
            'status' => 'active',
            'started_at' => now(),
        ], $attrs));
    }

    /** Первая подписка компании — новая; следующая — продление. */
    #[Test]
    public function новые_и_продления_различаются(): void
    {
        $fresh = Company::factory()->create();
        $this->subscription($fresh, ['started_at' => now()->startOfMonth()->addDay()]);

        $returning = Company::factory()->create();
        $this->subscription($returning, ['started_at' => now()->subMonths(3), 'status' => 'expired']);
        $this->subscription($returning, ['started_at' => now()->startOfMonth()->addDays(2)]);

        [$from, $to] = $this->period();
        $stats = FinanceReport::subscriptions($from, $to);

        $this->assertSame(1, $stats['new']);
        $this->assertSame(1, $stats['renewed']);
    }

    #[Test]
    public function явный_отказ_считается_отдельно(): void
    {
        $company = Company::factory()->create();
        $this->subscription($company, [
            'status' => 'cancelled',
            'started_at' => now()->subMonths(2),
            'cancelled_at' => now()->startOfMonth()->addDay(),
        ]);

        [$from, $to] = $this->period();

        $this->assertSame(1, FinanceReport::subscriptions($from, $to)['cancelled']);
    }

    /**
     * Молчаливый отток: срок вышел, новой подписки нет. Он опаснее
     * явного отказа — о нём никто не сообщает.
     */
    #[Test]
    public function истёкшая_без_продления_считается_оттоком(): void
    {
        $gone = Company::factory()->create();
        $this->subscription($gone, [
            'status' => 'expired',
            'started_at' => now()->subMonths(2),
            'ends_at' => now()->startOfMonth()->addDay(),
        ]);

        [$from, $to] = $this->period();

        $this->assertSame(1, FinanceReport::subscriptions($from, $to)['expired']);
    }

    /** Истекла и тут же продлена — это не отток. */
    #[Test]
    public function истёкшая_но_продлённая_оттоком_не_считается(): void
    {
        $stayed = Company::factory()->create();
        $this->subscription($stayed, [
            'status' => 'expired',
            'started_at' => now()->subMonths(2),
            'ends_at' => now()->startOfMonth()->addDay(),
        ]);
        $this->subscription($stayed, ['started_at' => now()->startOfMonth()->addDays(2)]);

        [$from, $to] = $this->period();

        $this->assertSame(0, FinanceReport::subscriptions($from, $to)['expired']);
    }
}
