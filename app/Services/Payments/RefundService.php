<?php

declare(strict_types=1);

namespace App\Services\Payments;

use App\Models\Payment;
use App\Models\Refund;
use App\Models\User;
use App\Support\AdminLog;
use Illuminate\Support\Facades\DB;
use RuntimeException;

/**
 * Проведение и отклонение возвратов.
 *
 * Возврат — единственная операция, которая двигает деньги обратно, и
 * потому у неё есть отдельная служба, а не кнопка в таблице: проверки
 * суммы, статуса платежа и записи в журнал должны выполняться все и
 * всегда, откуда бы возврат ни пришёл.
 */
class RefundService
{
    /**
     * Завести заявку на возврат.
     *
     * Больше остатка вернуть нельзя: частичные возвраты складываются,
     * и без этой проверки два возврата по половине суммы прошли бы,
     * а третий вернул бы деньги, которых не было.
     */
    public function request(Payment $payment, User $author, int $amount, string $reason): Refund
    {
        if ($payment->status !== 'paid') {
            throw new RuntimeException('Вернуть можно только оплаченный счёт.');
        }

        if ($amount <= 0 || $amount > $payment->refundableAmount()) {
            throw new RuntimeException(
                'Сумма возврата должна быть от 1 до '.number_format($payment->refundableAmount(), 0, ',', ' ').'.',
            );
        }

        $refund = Refund::create([
            'payment_id' => $payment->id,
            'company_id' => $payment->company_id,
            'amount' => $amount,
            'currency' => $payment->currency,
            'reason' => $reason,
            'status' => Refund::STATUS_REQUESTED,
            'created_by' => $author->id,
        ]);

        AdminLog::record('created', 'refunds', $refund, [
            'after' => ['сумма' => $refund->money(), 'счёт' => $payment->number],
        ], $reason, $author);

        return $refund;
    }

    /**
     * Провести возврат.
     *
     * Платёж не удаляется и не переписывается задним числом: он меняет
     * статус, а сумма и история остаются. Полный возврат помечает счёт
     * возвращённым, частичный оставляет его оплаченным — иначе отчёт
     * по выручке потеряет разницу.
     */
    public function approve(Refund $refund, User $decider, ?string $note = null): void
    {
        if ($refund->isDecided()) {
            throw new RuntimeException('Решение по этому возврату уже принято.');
        }

        DB::transaction(function () use ($refund, $decider, $note): void {
            $refund->forceFill([
                'status' => Refund::STATUS_DONE,
                'decided_by' => $decider->id,
                'decided_at' => now(),
                'decision_note' => $note,
            ])->save();

            $payment = $refund->payment;

            if ($payment !== null && $payment->refundableAmount() === 0) {
                $payment->forceFill(['status' => 'refunded'])->save();
            }
        });

        AdminLog::record('refunded', 'refunds', $refund, [
            'before' => ['статус' => 'Заявлен'],
            'after' => ['статус' => 'Проведён', 'сумма' => $refund->money()],
        ], $note ?? $refund->reason, $decider);
    }

    /** Отклонение — тоже решение, и оно тоже требует формулировки. */
    public function reject(Refund $refund, User $decider, string $note): void
    {
        if ($refund->isDecided()) {
            throw new RuntimeException('Решение по этому возврату уже принято.');
        }

        $refund->forceFill([
            'status' => Refund::STATUS_REJECTED,
            'decided_by' => $decider->id,
            'decided_at' => now(),
            'decision_note' => $note,
        ])->save();

        AdminLog::record('rejected', 'refunds', $refund, [
            'before' => ['статус' => 'Заявлен'],
            'after' => ['статус' => 'Отклонён'],
        ], $note, $decider);
    }
}
