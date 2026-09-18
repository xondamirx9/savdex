<?php

declare(strict_types=1);

namespace App\Filament\Pages;

use App\Support\AdminAccess;
use App\Support\Business;
use App\Support\FinanceReport;
use BackedEnum;
use Filament\Pages\Page;
use Filament\Support\Icons\Heroicon;
use Livewire\Attributes\Url;
use UnitEnum;

/**
 * Финансовые отчёты: выручка по периодам, по тарифам, по источникам,
 * продления и отток (§6.3 ТЗ).
 *
 * Страница, а не ресурс: отчёт не создают и не правят, его читают.
 *
 * Границы периода живут в адресе строки браузера: ссылку на «сентябрь»
 * нужно уметь переслать бухгалтеру, а не объяснять ему, какие даты
 * выставить.
 */
class FinanceReports extends Page
{
    /**
     * Только тем, кому положены финансы.
     *
     * Admin сюда не входит намеренно: по ТЗ он не видит финансы вовсе —
     * ни сумм, ни отчётов.
     */
    public static function canAccess(): bool
    {
        return AdminAccess::allows('finreports.view');
    }

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedChartBar;

    protected static ?string $navigationLabel = 'Финансовые отчёты';

    protected static string|UnitEnum|null $navigationGroup = 'Монетизация';

    protected static ?int $navigationSort = 8;

    protected string $view = 'filament.pages.finance-reports';

    #[Url]
    public string $from = '';

    #[Url]
    public string $to = '';

    public function mount(): void
    {
        // Умолчание — местный месяц: по UTC с полуночи до пяти утра
        // первого числа «этот месяц» был бы прошлым
        [$start, $end] = Business::currentMonth();

        $this->from = $this->from !== '' ? $this->from : $start;
        $this->to = $this->to !== '' ? $this->to : $end;
    }

    public function getTitle(): string
    {
        return 'Финансовые отчёты';
    }

    public function getSubheading(): ?string
    {
        return 'Выручка, тарифы, источники, продления и отток за выбранный период.';
    }

    /** Быстрые периоды: их выбирают в девяти случаях из десяти. */
    public function setPeriod(string $name): void
    {
        [$from, $to] = match ($name) {
            'prev' => [now()->subMonth()->startOfMonth(), now()->subMonth()->endOfMonth()],
            'quarter' => [now()->startOfQuarter(), now()->endOfQuarter()],
            'year' => [now()->startOfYear(), now()->endOfYear()],
            default => [now()->startOfMonth(), now()->endOfMonth()],
        };

        $this->from = $from->toDateString();
        $this->to = $to->toDateString();
    }

    /**
     * Границы периода.
     *
     * Конец дня, а не полночь: иначе платежи последнего дня месяца
     * выпадают из отчёта, и расхождение замечают не сразу.
     *
     * День — местный, ташкентский: хранится всё в UTC, а месяц человек
     * закрывает по своему календарю (см. Support\Business).
     */
    private function bounds(): array
    {
        return [
            Business::startOfDay($this->from !== '' ? $this->from : Business::currentMonth()[0]),
            Business::endOfDay($this->to !== '' ? $this->to : Business::currentMonth()[1]),
        ];
    }

    /** @return array<string, mixed> */
    public function getViewData(): array
    {
        [$from, $to] = $this->bounds();

        return [
            'revenue' => FinanceReport::revenue($from, $to),
            'months' => FinanceReport::byMonth($from, $to),
            'plans' => FinanceReport::byPlan($from, $to),
            'sources' => FinanceReport::bySource($from, $to),
            'subscriptions' => FinanceReport::subscriptions($from, $to),
        ];
    }
}
