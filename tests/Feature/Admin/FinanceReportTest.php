<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Models\Company;
use App\Models\Payment;
use App\Models\Plan;
use App\Models\Refund;
use App\Models\Subscription;
use App\Support\Business;
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

    /** Границы — как их строит страница: по местному календарю. */
    private function period(): array
    {
        [$start, $end] = Business::currentMonth();

        return [Business::startOfDay($start), Business::endOfDay($end)];
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
        $this->paid(100000, Business::startOfDay(Business::currentMonth()[0])->addDays(2));

        // Границы строятся так же, как их строит страница: по местному
        // календарю. Период, собранный в UTC, захватил бы лишний месяц —
        // конец месяца по UTC это уже первое число по Ташкенту
        $rows = FinanceReport::byMonth(
            Business::startOfDay(Business::today()->copy()->subMonths(2)->startOfMonth()->toDateString()),
            Business::endOfDay(Business::currentMonth()[1]),
        );

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

    // ── Дыры, найденные при проверке ────────────────────────────────

    /**
     * Полный возврат помечает счёт «возвращён», и он выпадал из
     * выручки: gross считался по status = paid.
     *
     * Последствие хуже разовой ошибки — отчёт менялся задним числом.
     * Сентябрьская выручка, посчитанная в октябре и в декабре, давала
     * разные числа, потому что между ними прошёл возврат.
     */
    #[Test]
    public function полностью_возвращённый_счёт_остаётся_в_поступлениях(): void
    {
        $payment = $this->paid(100000);

        Refund::query()->create([
            'payment_id' => $payment->id,
            'company_id' => $payment->company_id,
            'amount' => 100000,
            'currency' => 'UZS',
            'reason' => 'Полный возврат',
            'status' => Refund::STATUS_DONE,
            'decided_at' => now(),
        ]);
        $payment->forceFill(['status' => 'refunded'])->save();

        [$from, $to] = $this->period();
        $revenue = FinanceReport::revenue($from, $to);

        $this->assertSame(100000, $revenue['UZS']['gross'], 'деньги приходили — это факт периода');
        $this->assertSame(100000, $revenue['UZS']['refunded']);
        $this->assertSame(0, $revenue['UZS']['net'], 'пришло и ушло — ноль, а не минус сто тысяч');
        $this->assertSame(1, $revenue['UZS']['count']);
    }

    /** Возврат в следующем месяце не должен переписывать прошлый. */
    #[Test]
    public function возврат_не_переписывает_прошедший_месяц(): void
    {
        $payment = $this->paid(100000, now()->subMonth()->startOfMonth()->addDay());

        Refund::query()->create([
            'payment_id' => $payment->id,
            'company_id' => $payment->company_id,
            'amount' => 100000,
            'currency' => 'UZS',
            'reason' => 'Вернули позже',
            'status' => Refund::STATUS_DONE,
            'decided_at' => now(),
        ]);
        $payment->forceFill(['status' => 'refunded'])->save();

        $prev = FinanceReport::revenue(
            now()->subMonth()->startOfMonth(),
            now()->subMonth()->endOfMonth(),
        );

        $this->assertSame(100000, $prev['UZS']['gross'], 'в прошлом месяце деньги приходили');
        $this->assertSame(0, $prev['UZS']['refunded'], 'возврат прошёл в этом месяце, не в прошлом');
        $this->assertSame(100000, $prev['UZS']['net']);
    }

    /** Разбивки обязаны сходиться с общей выручкой, иначе им нельзя верить. */
    #[Test]
    public function разбивки_сходятся_с_общей_выручкой(): void
    {
        $refunded = $this->paid(100000);
        Refund::query()->create([
            'payment_id' => $refunded->id,
            'company_id' => $refunded->company_id,
            'amount' => 100000, 'currency' => 'UZS', 'reason' => 'Возврат',
            'status' => Refund::STATUS_DONE, 'decided_at' => now(),
        ]);
        $refunded->forceFill(['status' => 'refunded'])->save();

        $this->paid(50000, null, ['purpose' => 'credits']);

        [$from, $to] = $this->period();

        $gross = FinanceReport::revenue($from, $to)['UZS']['gross'];
        $byPlan = array_sum(array_column(FinanceReport::byPlan($from, $to), 'gross'));
        $bySource = array_sum(array_column(FinanceReport::bySource($from, $to), 'gross'));
        $byMonth = array_sum(array_column(FinanceReport::byMonth($from, $to), 'gross'));

        $this->assertSame(150000, $gross);
        $this->assertSame($gross, $byPlan, 'сумма по тарифам обязана сойтись с общей');
        $this->assertSame($gross, $bySource, 'сумма по источникам обязана сойтись с общей');
        $this->assertSame($gross, $byMonth, 'сумма по месяцам обязана сойтись с общей');
    }

    /**
     * Инфопанель и отчёт обязаны говорить одно и то же.
     *
     * Формула выручки жила в трёх местах: отчёт, показатели площадки
     * и виджет «оплачено сегодня». Разойдясь, они дали бы два экрана
     * с разной выручкой за один период — а человек, увидевший это,
     * перестаёт верить обоим.
     */
    #[Test]
    public function инфопанель_и_отчёт_считают_выручку_одинаково(): void
    {
        $kept = $this->paid(200000, now()->subDays(3));

        $returned = $this->paid(100000, now()->subDays(2));
        Refund::query()->create([
            'payment_id' => $returned->id,
            'company_id' => $returned->company_id,
            'amount' => 100000, 'currency' => 'UZS', 'reason' => 'Возврат',
            'status' => Refund::STATUS_DONE, 'decided_at' => now(),
        ]);
        $returned->forceFill(['status' => 'refunded'])->save();

        $fromReport = FinanceReport::revenue(now()->subMonth(), now())['UZS']['gross'];

        $fromDashboard = (int) Payment::query()
            ->received()
            ->whereBetween('paid_at', [now()->subMonth(), now()])
            ->sum('amount');

        $this->assertSame(300000, $fromReport);
        $this->assertSame($fromReport, $fromDashboard, 'два экрана не должны расходиться в деньгах');
    }

    /**
     * Граница месяца считается по ташкентскому календарю.
     *
     * Хранится всё в UTC. Оплата 1 октября в 02:00 по Ташкенту — это
     * 30 сентября 21:00 UTC, и в отчёте она уезжала в сентябрь.
     * Раз в месяц пять часов выручки оказывались в чужом периоде:
     * не потеря, но расхождение с тем, что человек закрывает как месяц.
     */
    #[Test]
    public function граница_месяца_по_местному_календарю(): void
    {
        // 1 октября 02:00 в Ташкенте = 30 сентября 21:00 UTC
        $payment = $this->paid(100000, Carbon::parse('2026-09-30 21:00:00', 'UTC'));

        $rows = FinanceReport::byMonth(
            Carbon::parse('2026-09-01 00:00:00', 'UTC'),
            Carbon::parse('2026-10-31 23:59:59', 'UTC'),
        );

        $september = collect($rows)->firstWhere('month', '2026-09');
        $october = collect($rows)->firstWhere('month', '2026-10');

        $this->assertSame(0, $september['gross'], 'по ташкентскому календарю это уже октябрь');
        $this->assertSame(100000, $october['gross']);
    }

    /** Часовой пояс дел берётся через config, а не env: конфиг на проде кэшируется. */
    #[Test]
    public function часовой_пояс_дел_переживает_кэш_конфигурации(): void
    {
        $this->assertSame('Asia/Tashkent', Business::timezone());

        config(['app.business_timezone' => 'Europe/Istanbul']);
        $this->assertSame('Europe/Istanbul', Business::timezone());
    }
}
