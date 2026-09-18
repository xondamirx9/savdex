<?php

declare(strict_types=1);

namespace App\Filament\Widgets;

use App\Filament\Pages\Invoices;
use App\Filament\Resources\Refunds\RefundResource;
use App\Models\Payment;
use App\Models\Refund;
use App\Support\AdminAccess;
use App\Support\Business;
use Filament\Widgets\StatsOverviewWidget;
use Filament\Widgets\StatsOverviewWidget\Stat;

/**
 * Деньги за сегодня — стартовый экран финансов.
 *
 * Три числа, на которые смотрят каждое утро: сколько пришло, сколько
 * ждёт подтверждения и сколько заявлено к возврату. Первое — про
 * выручку, два других — про долг перед клиентом.
 */
class FinanceToday extends StatsOverviewWidget
{
    protected ?string $heading = 'Деньги за сегодня';

    protected static ?int $sort = -26;

    public static function canView(): bool
    {
        return AdminAccess::allows('payments.view');
    }

    protected function getStats(): array
    {
        // «Сегодня» — ташкентское: по UTC с полуночи до пяти утра
        // сегодняшние оплаты считались вчерашними
        $paidToday = Payment::query()->received()
            ->whereBetween('paid_at', [
                Business::startOfDay(Business::today()->toDateString()),
                Business::endOfDay(Business::today()->toDateString()),
            ]);
        $pending = Payment::where('status', 'pending');
        $refunds = Refund::where('status', Refund::STATUS_REQUESTED);

        return [
            Stat::make('Оплачено сегодня', $this->money((int) $paidToday->sum('amount')))
                ->icon('heroicon-o-banknotes')
                ->description($this->plural($paidToday->count(), 'счёт', 'счёта', 'счетов'))
                ->color('success')
                ->url(Invoices::getUrl()),

            Stat::make('Ждут оплаты', (string) $pending->count())
                ->icon('heroicon-o-clock')
                // Выставленные, но неоплаченные — это ещё не выручка,
                // и путать их с ней нельзя
                ->description('на '.$this->money((int) $pending->sum('amount')))
                ->color($pending->count() > 0 ? 'warning' : 'gray')
                ->url(Invoices::getUrl()),

            Stat::make('Возвраты на решении', (string) $refunds->count())
                ->icon('heroicon-o-arrow-uturn-left')
                ->description($refunds->count() > 0
                    ? 'на '.$this->money((int) $refunds->sum('amount'))
                    : 'ничего не ждёт')
                ->color($refunds->count() > 0 ? 'danger' : 'gray')
                ->url(RefundResource::getUrl()),
        ];
    }

    private function money(int $amount): string
    {
        return number_format($amount, 0, ',', ' ').' сум';
    }

    private function plural(int $count, string $one, string $few, string $many): string
    {
        $mod100 = $count % 100;
        $mod10 = $count % 10;

        $word = match (true) {
            $mod100 >= 11 && $mod100 <= 14 => $many,
            $mod10 === 1 => $one,
            $mod10 >= 2 && $mod10 <= 4 => $few,
            default => $many,
        };

        return $count.' '.$word;
    }
}
