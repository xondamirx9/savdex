<?php

declare(strict_types=1);

namespace App\Filament\Pages;

use App\Support\AdminAccess;
use App\Support\FinanceReport;
use BackedEnum;
use Filament\Pages\Page;
use Filament\Support\Icons\Heroicon;
use Illuminate\Support\Carbon;
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
        $this->from = $this->from !== '' ? $this->from : now()->startOfMonth()->toDateString();
        $this->to = $this->to !== '' ? $this->to : now()->endOfMonth()->toDateString();
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
     */
    private function bounds(): array
    {
        return [
            Carbon::parse($this->from !== '' ? $this->from : now()->startOfMonth())->startOfDay(),
            Carbon::parse($this->to !== '' ? $this->to : now()->endOfMonth())->endOfDay(),
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
