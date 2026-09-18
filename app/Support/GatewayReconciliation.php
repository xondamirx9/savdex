<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\Payment;
use App\Models\PaymentTransaction;
use Illuminate\Support\Carbon;

/**
 * Сверка: что площадка начислила против того, что провёл шлюз (§6.3 ТЗ).
 *
 * Своя сторона — таблица payments: закрыт счёт или нет. Сторона шлюза —
 * payment_transactions: протокол вроде Payme или Uzum заводит транзакцию
 * сам и отдельными вызовами её проводит или отменяет. В исправном мире
 * эти две стороны говорят одно и то же.
 *
 * Расходятся они молча. Оборванный колбэк, откат базы, повторная
 * попытка оплаты — и счёт закрыт без денег или деньги взяты без
 * начисления. Ни то, ни другое не всплывает само: первое замечает
 * бухгалтерия в конце квартала, второе — клиент, и сразу публично.
 *
 * Поэтому экран ищет не «ошибки», а несогласия между двумя записями
 * одного события, и называет каждое своим именем.
 */
final class GatewayReconciliation
{
    /** Счёт закрыт, проведённой транзакции нет: начислили без денег. */
    public const PAID_WITHOUT_TRANSACTION = 'paid_without_transaction';

    /** Транзакция проведена, счёт не закрыт: деньги взяли, не начислили. */
    public const PERFORMED_WITHOUT_PAID = 'performed_without_paid';

    /** Суммы своей и чужой стороны не совпали. */
    public const AMOUNT_MISMATCH = 'amount_mismatch';

    /** На одном счёте больше одной проведённой транзакции: двойное списание. */
    public const DOUBLE_PERFORMED = 'double_performed';

    /** Возврат проведён у нас, транзакция шлюза не отменена. */
    public const REFUNDED_WITHOUT_CANCEL = 'refunded_without_cancel';

    /**
     * Насколько это срочно и как называется.
     *
     * Порядок важнее подписей: «деньги взяли и не начислили» — это
     * жалоба клиента, которая ещё не поступила, и она обязана стоять
     * первой, даже если таких строк одна, а прочих сто.
     *
     * @var array<string, array{title: string, hint: string, severity: string}>
     */
    public const KINDS = [
        self::PERFORMED_WITHOUT_PAID => [
            'title' => 'Деньги взяты, счёт не закрыт',
            'hint' => 'Шлюз провёл транзакцию, а площадка счёт не закрыла и ничего не начислила. Клиент заплатил и не получил. Разбирать первым.',
            'severity' => 'danger',
        ],
        self::DOUBLE_PERFORMED => [
            'title' => 'Двойное списание',
            'hint' => 'На одном счёте больше одной проведённой транзакции. Скорее всего с клиента списали дважды — проверить и вернуть.',
            'severity' => 'danger',
        ],
        self::AMOUNT_MISMATCH => [
            'title' => 'Суммы расходятся',
            'hint' => 'Площадка и шлюз записали разные суммы по одному счёту.',
            'severity' => 'danger',
        ],
        self::PAID_WITHOUT_TRANSACTION => [
            'title' => 'Счёт закрыт без транзакции шлюза',
            'hint' => 'Площадка начислила, подтверждения от шлюза нет. Бывает законно — оплата заведена вручную администратором; тогда в счёте есть отметка о том, кто подтвердил.',
            'severity' => 'warning',
        ],
        self::REFUNDED_WITHOUT_CANCEL => [
            'title' => 'Возврат без отмены у шлюза',
            'hint' => 'Площадка считает платёж возвращённым, транзакция шлюза не отменена. Деньги могли не уйти клиенту.',
            'severity' => 'warning',
        ],
    ];

    /**
     * Все расхождения за период, в порядке срочности.
     *
     * Период считается по дате счёта, а не по дате транзакции: счёт —
     * то, что ищет человек, разбирающий расхождение.
     *
     * @return list<array{kind: string, payment_id: int|null, number: string|null, company: string|null, ours: int|null, theirs: int|null, currency: string, at: Carbon|null, note: string|null}>
     */
    public static function findings(Carbon $from, Carbon $to): array
    {
        $payments = Payment::query()
            ->whereBetween('created_at', [$from, $to])
            ->with(['company:id,name', 'transactions'])
            ->get();

        $found = [];

        foreach ($payments as $payment) {
            $performed = $payment->transactions
                ->where('state', PaymentTransaction::STATE_PERFORMED);

            $company = $payment->company?->name;

            if ($payment->status === 'paid' && $performed->isEmpty()) {
                $found[] = self::row(self::PAID_WITHOUT_TRANSACTION, $payment, $company, $payment->amount, null,
                    $payment->confirmed_by !== null ? 'Подтверждён вручную администратором' : null);

                continue;
            }

            if ($payment->status !== 'paid' && $payment->status !== 'refunded' && $performed->isNotEmpty()) {
                $found[] = self::row(self::PERFORMED_WITHOUT_PAID, $payment, $company,
                    $payment->amount, (int) $performed->sum('amount_minor'), null);

                continue;
            }

            if ($performed->count() > 1) {
                $found[] = self::row(self::DOUBLE_PERFORMED, $payment, $company,
                    $payment->amount, (int) $performed->sum('amount_minor'),
                    $performed->count().' проведённых транзакции');

                continue;
            }

            $single = $performed->first();

            if ($single !== null && self::differs($payment, $single)) {
                $found[] = self::row(self::AMOUNT_MISMATCH, $payment, $company,
                    $payment->amount, (int) $single->amount_minor, null);

                continue;
            }

            if ($payment->status === 'refunded' && $performed->isNotEmpty()) {
                $found[] = self::row(self::REFUNDED_WITHOUT_CANCEL, $payment, $company,
                    $payment->amount, (int) $performed->sum('amount_minor'), null);
            }
        }

        // Порядок объявления KINDS — это порядок срочности
        $order = array_flip(array_keys(self::KINDS));
        usort($found, fn (array $a, array $b): int => $order[$a['kind']] <=> $order[$b['kind']]);

        return $found;
    }

    /**
     * Сходятся ли суммы.
     *
     * Своя сторона хранит сумму в сумах, сторона шлюза — в минорных
     * единицах (тийинах). Сравнение без приведения показало бы
     * расхождение на каждом исправном платеже.
     */
    private static function differs(Payment $payment, PaymentTransaction $transaction): bool
    {
        return $payment->amountMinor() !== (int) $transaction->amount_minor;
    }

    /**
     * @return array{kind: string, payment_id: int|null, number: string|null, company: string|null, ours: int|null, theirs: int|null, currency: string, at: Carbon|null, note: string|null}
     */
    private static function row(string $kind, Payment $payment, ?string $company, ?int $ours, ?int $theirs, ?string $note): array
    {
        return [
            'kind' => $kind,
            'payment_id' => $payment->id,
            'number' => $payment->number,
            'company' => $company,
            'ours' => $ours,
            'theirs' => $theirs,
            'currency' => $payment->currency ?? 'UZS',
            'at' => $payment->created_at,
            'note' => $note,
        ];
    }

    /**
     * Сводка по видам — чтобы понять состояние, не читая список.
     *
     * @return array<string, int>
     */
    public static function summary(Carbon $from, Carbon $to): array
    {
        $counts = array_fill_keys(array_keys(self::KINDS), 0);

        foreach (self::findings($from, $to) as $finding) {
            $counts[$finding['kind']]++;
        }

        return $counts;
    }
}
