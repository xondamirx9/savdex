<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\Payment;
use App\Models\Refund;
use App\Models\Subscription;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Support\Carbon;
use Illuminate\Support\Collection;

/**
 * Финансовые отчёты: выручка по периодам, по тарифам, по источникам,
 * продления и отток (§6.3 ТЗ).
 *
 * Считается здесь, а не в странице: у каждого числа есть определение,
 * и определение должно быть проверяемо тестом, а не вычитываться
 * из вёрстки.
 *
 * Группировка по месяцам делается в PHP, а не в SQL. Функции работы
 * с датами у SQLite и PostgreSQL разные, а тесты идут на первой,
 * боевая площадка на второй: отчёт, который сходится в тестах и врёт
 * на проде, хуже отсутствующего. Объёмы это позволяют — счетов сотни,
 * не миллионы.
 */
final class FinanceReport
{
    /**
     * Счета, по которым деньги действительно пришли в периоде.
     *
     * Определение прихода — одно на всю площадку, в Payment::scopeReceived:
     * не `status = paid`, иначе полностью возвращённый счёт выпадал бы
     * из выручки вместе с месяцем, в котором деньги приходили.
     *
     * @param  Builder<Payment>  $query
     * @return Builder<Payment>
     */
    private static function received(Carbon $from, Carbon $to): Builder
    {
        return Payment::query()
            ->received()
            ->whereBetween('paid_at', [$from, $to]);
    }

    /**
     * Выручка за период, по валютам.
     *
     * Валюты не складываются: сумма сумов и долларов — не деньги,
     * а число. Сегодня все платежи в UZS (OrderService проставляет
     * её жёстко), но столбец в базе есть, и отчёт обязан пережить
     * появление второй валюты, а не молча посчитать её как первую.
     *
     * Возвраты вычитаются по дате возврата, а не по дате платежа:
     * деньги ушли из кассы тогда, когда их вернули.
     *
     * @return array<string, array{gross: int, refunded: int, net: int, count: int}>
     */
    public static function revenue(Carbon $from, Carbon $to): array
    {
        $paid = self::received($from, $to)->get(['currency', 'amount']);

        $refunded = Refund::query()
            ->where('status', Refund::STATUS_DONE)
            ->whereBetween('decided_at', [$from, $to])
            ->get(['currency', 'amount']);

        $rows = [];

        foreach ($paid->groupBy('currency') as $currency => $payments) {
            $rows[$currency] = [
                'gross' => (int) $payments->sum('amount'),
                'refunded' => 0,
                'net' => (int) $payments->sum('amount'),
                'count' => $payments->count(),
            ];
        }

        foreach ($refunded as $refund) {
            $currency = $refund->currency ?? 'UZS';

            $rows[$currency] ??= ['gross' => 0, 'refunded' => 0, 'net' => 0, 'count' => 0];
            $rows[$currency]['refunded'] += (int) $refund->amount;
            $rows[$currency]['net'] -= (int) $refund->amount;
        }

        return $rows;
    }

    /**
     * Выручка по месяцам — то, по чему видно рост или падение.
     *
     * Возвращаются все месяцы диапазона, включая пустые: месяц без
     * единой продажи — это факт, а не отсутствие строки.
     *
     * @return list<array{month: string, label: string, gross: int, refunded: int, net: int, count: int}>
     */
    public static function byMonth(Carbon $from, Carbon $to): array
    {
        $paid = self::received($from, $to)
            ->get(['paid_at', 'amount'])
            ->groupBy(fn (Payment $p): string => Business::local($p->paid_at)->format('Y-m'));

        $refunds = Refund::query()
            ->where('status', Refund::STATUS_DONE)
            ->whereBetween('decided_at', [$from, $to])
            ->get(['decided_at', 'amount'])
            ->groupBy(fn (Refund $r): string => Business::local($r->decided_at)->format('Y-m'));

        // Обход месяцев тоже по местному календарю: иначе последний
        // месяц диапазона мог не появиться в списке вовсе
        $rows = [];
        $cursor = Business::local($from)->startOfMonth();
        $last = Business::local($to)->startOfMonth();

        while ($cursor->lessThanOrEqualTo($last)) {
            $key = $cursor->format('Y-m');

            // get(), а не [$key]: обращение к отсутствующему ключу
            // коллекции — исключение, и месяц без единой продажи
            // ронял бы весь отчёт
            $month = $paid->get($key);
            $back = (int) ($refunds->get($key)?->sum('amount') ?? 0);
            $gross = (int) ($month?->sum('amount') ?? 0);

            $rows[] = [
                'month' => $key,
                'label' => $cursor->translatedFormat('F Y'),
                'gross' => $gross,
                'refunded' => $back,
                'net' => $gross - $back,
                'count' => (int) ($month?->count() ?? 0),
            ];

            $cursor->addMonth();
        }

        return $rows;
    }

    /**
     * Выручка по тарифам: за что именно платят.
     *
     * @return list<array{name: string, count: int, gross: int}>
     */
    public static function byPlan(Carbon $from, Carbon $to): array
    {
        return self::received($from, $to)
            ->with('plan:id,name')
            ->get(['plan_id', 'amount'])
            ->groupBy(fn (Payment $p): string => $p->plan?->name ?? 'Без тарифа')
            ->map(fn (Collection $group, string $name): array => [
                'name' => $name,
                'count' => $group->count(),
                'gross' => (int) $group->sum('amount'),
            ])
            ->sortByDesc('gross')
            ->values()
            ->all();
    }

    /** Назначения платежей — те же слова, что в кабинете покупателя. */
    public const PURPOSES = [
        'subscription' => 'Подписка',
        'credits' => 'Пакет контактов',
        'promo_units' => 'Продвижение',
    ];

    /**
     * Выручка по источникам: назначение платежа и платёжный шлюз.
     *
     * @return list<array{purpose: string, provider: string, count: int, gross: int}>
     */
    public static function bySource(Carbon $from, Carbon $to): array
    {
        return self::received($from, $to)
            ->get(['purpose', 'provider', 'amount'])
            ->groupBy(fn (Payment $p): string => $p->purpose.'|'.($p->provider ?? ''))
            ->map(function (Collection $group, string $key): array {
                [$purpose, $provider] = explode('|', $key, 2);

                return [
                    'purpose' => self::PURPOSES[$purpose] ?? $purpose,
                    'provider' => $provider !== '' ? $provider : 'не указан',
                    'count' => $group->count(),
                    'gross' => (int) $group->sum('amount'),
                ];
            })
            ->sortByDesc('gross')
            ->values()
            ->all();
    }

    /**
     * Продления и отток.
     *
     * У каждого числа здесь своё определение, и определения важнее
     * самих чисел — «отток 12%» без уточнения, что считали, не значит
     * ничего:
     *
     *  - новые      — подписка началась в периоде, и до неё у компании
     *                 подписок не было вовсе;
     *  - продления  — подписка началась в периоде, и раньше у компании
     *                 уже была хоть одна;
     *  - отменили   — компания сама отказалась (cancelled_at в периоде);
     *  - истекли    — срок вышел в периоде, и новой подписки компания
     *                 не завела. Это молчаливый отток, он опаснее
     *                 явного отказа: о нём никто не сообщает.
     *
     * @return array{new: int, renewed: int, cancelled: int, expired: int, active: int}
     */
    public static function subscriptions(Carbon $from, Carbon $to): array
    {
        $started = Subscription::query()
            ->whereBetween('started_at', [$from, $to])
            ->get(['id', 'company_id', 'started_at']);

        /*
         * Самая ранняя подписка каждой компании — одним запросом.
         *
         * Раньше на каждую подписку периода шёл отдельный exists():
         * шестьдесят подписок давали шестьдесят четыре запроса, а на
         * годовом отчёте это тысячи. Проверка «была ли раньше хоть
         * одна» равносильна сравнению с самой ранней, и она берётся
         * разом.
         */
        $firstEver = Subscription::query()
            ->whereIn('company_id', $started->pluck('company_id')->unique())
            ->selectRaw('company_id, MIN(started_at) as first_started_at')
            ->groupBy('company_id')
            ->pluck('first_started_at', 'company_id');

        $new = 0;
        $renewed = 0;

        foreach ($started as $subscription) {
            $first = $firstEver[$subscription->company_id] ?? null;

            $hadEarlier = $first !== null
                && Carbon::parse($first)->lessThan($subscription->started_at);

            $hadEarlier ? $renewed++ : $new++;
        }

        $cancelled = Subscription::query()
            ->whereBetween('cancelled_at', [$from, $to])
            ->count();

        $ended = Subscription::query()
            ->where('status', 'expired')
            ->whereBetween('ends_at', [$from, $to])
            ->get(['company_id', 'ends_at']);

        // Самая поздняя подписка тех же компаний — тоже одним запросом,
        // по той же причине, что и самая ранняя выше
        $lastEver = Subscription::query()
            ->whereIn('company_id', $ended->pluck('company_id')->unique())
            ->selectRaw('company_id, MAX(started_at) as last_started_at')
            ->groupBy('company_id')
            ->pluck('last_started_at', 'company_id');

        $expired = $ended
            ->reject(function (Subscription $subscription) use ($lastEver): bool {
                $last = $lastEver[$subscription->company_id] ?? null;

                // Завела новую подписку после того, как истекла старая,
                // — значит не ушла
                return $last !== null
                    && Carbon::parse($last)->greaterThanOrEqualTo($subscription->ends_at);
            })
            ->count();

        $active = Subscription::query()
            ->where('status', 'active')
            ->where('started_at', '<=', $to)
            ->where(fn ($q) => $q->whereNull('ends_at')->orWhere('ends_at', '>=', $to))
            ->count();

        return compact('new', 'renewed', 'cancelled', 'expired', 'active');
    }
}
