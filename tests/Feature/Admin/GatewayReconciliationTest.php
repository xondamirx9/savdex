<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Models\Company;
use App\Models\Payment;
use App\Models\PaymentTransaction;
use App\Models\User;
use App\Support\GatewayReconciliation as Recon;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Carbon;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Сверка со шлюзом.
 *
 * Расхождения между своей стороной и стороной шлюза не всплывают сами:
 * «начислили без денег» замечает бухгалтерия в конце квартала, «деньги
 * взяли и не начислили» — клиент, и сразу публично. Поэтому здесь
 * каждый вид расхождения подстроен намеренно и проверен поимённо.
 */
class GatewayReconciliationTest extends TestCase
{
    use RefreshDatabase;

    private function payment(string $status, int $amount = 100000, array $extra = []): Payment
    {
        return Payment::query()->create(array_merge([
            'company_id' => Company::factory()->create()->id,
            'number' => 'SD-'.fake()->unique()->numberBetween(1000, 9999),
            'purpose' => 'subscription',
            'description' => 'Тариф «Бизнес»',
            'amount' => $amount,
            'currency' => 'UZS',
            'provider' => 'uzum',
            'status' => $status,
            'paid_at' => $status === 'paid' ? now() : null,
        ], $extra));
    }

    private function transaction(Payment $payment, string $state, ?int $amountMinor = null): PaymentTransaction
    {
        return PaymentTransaction::query()->create([
            'payment_id' => $payment->id,
            'provider' => 'uzum',
            'provider_transaction_id' => fake()->unique()->uuid(),
            'state' => $state,
            'amount_minor' => $amountMinor ?? $payment->amountMinor(),
            'currency' => 'UZS',
            'payload' => [],
            'performed_at' => $state === PaymentTransaction::STATE_PERFORMED ? now() : null,
        ]);
    }

    /** @return list<string> виды найденных расхождений */
    private function kinds(): array
    {
        return array_column(Recon::findings(now()->subMonth(), now()->addDay()), 'kind');
    }

    // ── Исправный случай ────────────────────────────────────────────

    /** Самое важное: исправный платёж не должен попадать в список. */
    #[Test]
    public function сошедшийся_платёж_расхождением_не_считается(): void
    {
        $payment = $this->payment('paid');
        $this->transaction($payment, PaymentTransaction::STATE_PERFORMED);

        $this->assertSame([], $this->kinds(), 'исправный платёж не должен попадать в сверку');
    }

    /** Незакрытый счёт без транзакций — это не расхождение, а неоплаченный счёт. */
    #[Test]
    public function ожидающий_оплаты_счёт_расхождением_не_считается(): void
    {
        $this->payment('pending');

        $this->assertSame([], $this->kinds());
    }

    /** Отменённая попытка рядом с удачной — обычная жизнь протокола. */
    #[Test]
    public function отменённая_попытка_рядом_с_удачной_не_мешает(): void
    {
        $payment = $this->payment('paid');
        $this->transaction($payment, PaymentTransaction::STATE_CANCELLED);
        $this->transaction($payment, PaymentTransaction::STATE_PERFORMED);

        $this->assertSame([], $this->kinds());
    }

    // ── Расхождения ─────────────────────────────────────────────────

    /** Худший случай: клиент заплатил и ничего не получил. */
    #[Test]
    public function деньги_взяты_а_счёт_не_закрыт(): void
    {
        $payment = $this->payment('pending');
        $this->transaction($payment, PaymentTransaction::STATE_PERFORMED);

        $this->assertSame([Recon::PERFORMED_WITHOUT_PAID], $this->kinds());
    }

    #[Test]
    public function счёт_закрыт_без_транзакции_шлюза(): void
    {
        $this->payment('paid');

        $this->assertSame([Recon::PAID_WITHOUT_TRANSACTION], $this->kinds());
    }

    /** Оплата, заведённая администратором вручную, — законный случай, и это видно. */
    #[Test]
    public function ручное_подтверждение_помечается_пояснением(): void
    {
        $admin = User::factory()->create(['is_admin' => true]);
        $this->payment('paid', 100000, ['confirmed_by' => $admin->id]);

        $findings = Recon::findings(now()->subMonth(), now()->addDay());

        $this->assertSame(Recon::PAID_WITHOUT_TRANSACTION, $findings[0]['kind']);
        $this->assertSame('Подтверждён вручную администратором', $findings[0]['note']);
    }

    #[Test]
    public function двойное_списание(): void
    {
        $payment = $this->payment('paid');
        $this->transaction($payment, PaymentTransaction::STATE_PERFORMED);
        $this->transaction($payment, PaymentTransaction::STATE_PERFORMED);

        $this->assertSame([Recon::DOUBLE_PERFORMED], $this->kinds());
    }

    /** Своя сторона в сумах, сторона шлюза в тийинах: без приведения расходился бы каждый платёж. */
    #[Test]
    public function суммы_сравниваются_в_одних_единицах(): void
    {
        $payment = $this->payment('paid', 100000);
        $this->transaction($payment, PaymentTransaction::STATE_PERFORMED, 100000 * 100);

        $this->assertSame([], $this->kinds(), '10 000 000 тийин это и есть 100 000 сум');
    }

    #[Test]
    public function расхождение_сумм(): void
    {
        $payment = $this->payment('paid', 100000);
        $this->transaction($payment, PaymentTransaction::STATE_PERFORMED, 90000 * 100);

        $findings = Recon::findings(now()->subMonth(), now()->addDay());

        $this->assertSame([Recon::AMOUNT_MISMATCH], array_column($findings, 'kind'));
        $this->assertSame(100000, $findings[0]['ours']);
        $this->assertSame(9000000, $findings[0]['theirs']);
    }

    /**
     * Обычный возврат расхождением не считается.
     *
     * Площадка не отменяет транзакцию у шлюза: UzumGateway::refund()
     * не подключён, возврат оформляют руками в кабинете Uzum. Значит
     * «счёт возвращён, транзакция проведена» — это состояние КАЖДОГО
     * возврата, а не расхождение. Экран, который загорается на каждом
     * обычном событии, перестают открывать, и настоящее расхождение
     * тонет вместе с ложными.
     */
    #[Test]
    public function обычный_возврат_расхождением_не_считается(): void
    {
        $payment = $this->payment('refunded');
        $this->transaction($payment, PaymentTransaction::STATE_PERFORMED);

        $this->assertSame([], $this->kinds());
    }

    #[Test]
    public function возврат_с_отменённой_транзакцией_расхождением_не_считается(): void
    {
        $payment = $this->payment('refunded');
        $this->transaction($payment, PaymentTransaction::STATE_CANCELLED);

        $this->assertSame([], $this->kinds());
    }

    // ── Порядок и сводка ────────────────────────────────────────────

    /**
     * Срочное — сверху. Одна строка «деньги взяли и не начислили»
     * важнее сотни «закрыт без транзакции», и искать её пролистыванием
     * человек не должен.
     */
    #[Test]
    public function срочное_идёт_первым(): void
    {
        $this->payment('paid');
        $this->payment('paid');

        $unpaid = $this->payment('pending');
        $this->transaction($unpaid, PaymentTransaction::STATE_PERFORMED);

        $this->assertSame(Recon::PERFORMED_WITHOUT_PAID, $this->kinds()[0]);
    }

    #[Test]
    public function сводка_считает_по_видам(): void
    {
        $this->payment('paid');
        $unpaid = $this->payment('pending');
        $this->transaction($unpaid, PaymentTransaction::STATE_PERFORMED);

        $summary = Recon::summary(now()->subMonth(), now()->addDay());

        $this->assertSame(1, $summary[Recon::PAID_WITHOUT_TRANSACTION]);
        $this->assertSame(1, $summary[Recon::PERFORMED_WITHOUT_PAID]);
        $this->assertSame(0, $summary[Recon::DOUBLE_PERFORMED]);
    }

    /**
     * Полностью прошлое остаётся в прошлом.
     *
     * Счёт заведён и оплачен полгода назад, транзакций в периоде нет —
     * в месячную сверку он не попадает. Иначе список рос бы вечно
     * и перестал быть рабочим.
     */
    #[Test]
    public function период_ограничивает_выборку(): void
    {
        $old = $this->payment('paid');
        $old->forceFill([
            'created_at' => Carbon::now()->subMonths(6),
            'paid_at' => Carbon::now()->subMonths(6),
        ])->save();

        $this->assertSame(
            [],
            array_column(Recon::findings(now()->startOfMonth(), now()->endOfMonth()), 'kind'),
            'счёт полугодовой давности не должен попадать в месячную сверку',
        );
    }

    /**
     * Период считается по движению денег, а не только по дате счёта.
     *
     * Счёт выставили в августе, оплатили в сентябре — расхождение
     * по нему обязано попасть в сентябрьскую сверку. Иначе его
     * не увидит никто: в августе его ещё не было, в сентябре
     * выборка по created_at его не берёт.
     */
    #[Test]
    public function счёт_из_прошлого_месяца_оплаченный_в_этом_попадает_в_сверку(): void
    {
        $payment = $this->payment('pending');
        $payment->forceFill(['created_at' => Carbon::now()->subMonths(2)])->save();

        $this->transaction($payment, PaymentTransaction::STATE_PERFORMED);

        $this->assertSame(
            [Recon::PERFORMED_WITHOUT_PAID],
            array_column(Recon::findings(now()->startOfMonth(), now()->endOfMonth()), 'kind'),
        );
    }
}
