<?php

declare(strict_types=1);

namespace Tests\Feature\Finance;

use App\Filament\Pages\FinanceOperations;
use App\Filament\Resources\Refunds\RefundResource;
use App\Models\AdminAction;
use App\Models\Company;
use App\Models\Payment;
use App\Models\Refund;
use App\Models\User;
use App\Services\Payments\RefundService;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use RuntimeException;
use Tests\TestCase;

/**
 * Возвраты и финансовые операции.
 *
 * Здесь проверяется то, из-за чего возвраты и вынесены в отдельную
 * службу: нельзя вернуть больше, чем заплатили, нельзя решить дважды
 * и нельзя сделать это молча.
 */
class RefundsTest extends TestCase
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

    private function payment(int $amount = 1000000, string $status = 'paid'): Payment
    {
        return Payment::create([
            'company_id' => Company::factory()->create()->id,
            'purpose' => 'credits',
            'description' => 'Пакет контактов',
            'amount' => $amount,
            'currency' => 'UZS',
            'status' => $status,
            'paid_at' => now(),
        ]);
    }

    private function service(): RefundService
    {
        return app(RefundService::class);
    }

    // ── Кто видит раздел ────────────────────────────────────────────

    #[Test]
    public function возвраты_видят_только_финансы_и_суперадмин(): void
    {
        foreach (AdminAccess::ROLES as $role => $label) {
            $this->actingAs($this->admin($role));

            $expected = in_array($role, [AdminAccess::SUPERADMIN, AdminAccess::FINANCE], true);

            $this->assertSame($expected, RefundResource::canViewAny(), $label);
            $this->assertSame($expected, FinanceOperations::canAccess(), $label);
        }
    }

    /** Администратор финансов не видит — ни сумм, ни возвратов. */
    #[Test]
    public function администратор_возвраты_не_видит(): void
    {
        $this->actingAs($this->admin(AdminAccess::ADMIN));

        $this->assertFalse(RefundResource::canViewAny());
    }

    // ── Заявка ──────────────────────────────────────────────────────

    #[Test]
    public function финансист_заявляет_возврат(): void
    {
        $finance = $this->admin(AdminAccess::FINANCE);
        $this->actingAs($finance);

        $payment = $this->payment(1000000);

        $refund = $this->service()->request($payment, $finance, 400000, 'Оплата прошла дважды');

        $this->assertSame(Refund::STATUS_REQUESTED, $refund->status);
        $this->assertSame(400000, $refund->amount);
        $this->assertSame($payment->company_id, $refund->company_id);
    }

    /** Неоплаченный счёт возвращать нечего. */
    #[Test]
    public function по_неоплаченному_счёту_возврата_нет(): void
    {
        $finance = $this->admin(AdminAccess::FINANCE);
        $this->actingAs($finance);

        $this->expectException(RuntimeException::class);

        $this->service()->request($this->payment(1000000, 'pending'), $finance, 100, 'Причина возврата');
    }

    #[Test]
    public function больше_суммы_счёта_вернуть_нельзя(): void
    {
        $finance = $this->admin(AdminAccess::FINANCE);
        $this->actingAs($finance);

        $this->expectException(RuntimeException::class);

        $this->service()->request($this->payment(1000000), $finance, 1000001, 'Причина возврата');
    }

    /**
     * Частичные возвраты складываются.
     *
     * Без учёта уже возвращённого два возврата по половине суммы прошли
     * бы, а третий вернул бы деньги, которых не было.
     */
    #[Test]
    public function частичные_возвраты_складываются(): void
    {
        $finance = $this->admin(AdminAccess::FINANCE);
        $this->actingAs($finance);

        $payment = $this->payment(1000000);

        $first = $this->service()->request($payment, $finance, 600000, 'Первая часть возврата');
        $this->service()->approve($first, $finance);

        $this->assertSame(400000, $payment->fresh()->refundableAmount());

        $this->expectException(RuntimeException::class);

        $this->service()->request($payment->fresh(), $finance, 500000, 'Вторая часть возврата');
    }

    // ── Решение ─────────────────────────────────────────────────────

    /** Полный возврат помечает счёт возвращённым. */
    #[Test]
    public function полный_возврат_меняет_статус_счёта(): void
    {
        $finance = $this->admin(AdminAccess::FINANCE);
        $this->actingAs($finance);

        $payment = $this->payment(1000000);
        $refund = $this->service()->request($payment, $finance, 1000000, 'Услуга не оказана');

        $this->service()->approve($refund, $finance, 'Подтверждено выпиской');

        $this->assertSame('refunded', $payment->fresh()->status);
        $this->assertSame(Refund::STATUS_DONE, $refund->fresh()->status);
        $this->assertNotNull($refund->fresh()->decided_at);
    }

    /**
     * Частичный возврат оставляет счёт оплаченным.
     *
     * Иначе отчёт по выручке потеряет разницу между тем, что заплатили,
     * и тем, что вернули.
     */
    #[Test]
    public function частичный_возврат_оставляет_счёт_оплаченным(): void
    {
        $finance = $this->admin(AdminAccess::FINANCE);
        $this->actingAs($finance);

        $payment = $this->payment(1000000);
        $refund = $this->service()->request($payment, $finance, 300000, 'Вернули часть по договорённости');

        $this->service()->approve($refund, $finance);

        $this->assertSame('paid', $payment->fresh()->status);
        $this->assertSame(700000, $payment->fresh()->refundableAmount());
    }

    #[Test]
    public function решение_принимается_один_раз(): void
    {
        $finance = $this->admin(AdminAccess::FINANCE);
        $this->actingAs($finance);

        $payment = $this->payment(1000000);
        $refund = $this->service()->request($payment, $finance, 100000, 'Причина возврата');

        $this->service()->approve($refund, $finance);

        $this->expectException(RuntimeException::class);

        $this->service()->approve($refund->fresh(), $finance);
    }

    #[Test]
    public function отклонённый_возврат_счёт_не_трогает(): void
    {
        $finance = $this->admin(AdminAccess::FINANCE);
        $this->actingAs($finance);

        $payment = $this->payment(1000000);
        $refund = $this->service()->request($payment, $finance, 1000000, 'Клиент передумал');

        $this->service()->reject($refund, $finance, 'Услуга оказана в полном объёме');

        $this->assertSame('paid', $payment->fresh()->status);
        $this->assertSame(Refund::STATUS_REJECTED, $refund->fresh()->status);
        $this->assertSame(1000000, $payment->fresh()->refundableAmount());
    }

    // ── Запись не стирается ─────────────────────────────────────────

    /**
     * Ошибочный возврат исправляется обратной операцией, а не стиранием.
     *
     * Удалённый возврат ничем не отличается от возврата, которого не было.
     */
    #[Test]
    public function возврат_нельзя_удалить_или_отредактировать(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPERADMIN));

        $refund = Refund::factory()->create(['payment_id' => $this->payment()->id]);

        $this->assertFalse(RefundResource::canEdit($refund));
        $this->assertFalse(RefundResource::canDelete($refund));
        $this->assertFalse(RefundResource::canForceDelete($refund));
    }

    // ── След в журнале ──────────────────────────────────────────────

    #[Test]
    public function проведение_возврата_попадает_в_журнал(): void
    {
        $finance = $this->admin(AdminAccess::FINANCE);
        $this->actingAs($finance);

        $payment = $this->payment(1000000);
        $refund = $this->service()->request($payment, $finance, 250000, 'Двойное списание');

        $this->service()->approve($refund, $finance, 'Подтверждено выпиской');

        $entry = AdminAction::where('action', 'refunded')->sole();

        $this->assertSame('refunds', $entry->section);
        $this->assertSame($finance->id, $entry->user_id);
        $this->assertSame('Подтверждено выпиской', $entry->note);
        $this->assertSame('Проведён', $entry->changes['after']['статус']);
    }

    #[Test]
    public function отклонение_тоже_попадает_в_журнал(): void
    {
        $finance = $this->admin(AdminAccess::FINANCE);
        $this->actingAs($finance);

        $refund = $this->service()->request($this->payment(), $finance, 1000, 'Причина возврата');

        $this->service()->reject($refund, $finance, 'Основания не подтвердились');

        $this->assertTrue(
            AdminAction::where('section', 'refunds')->where('action', 'rejected')->exists(),
        );
    }
}
