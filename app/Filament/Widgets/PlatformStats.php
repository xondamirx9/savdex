<?php

declare(strict_types=1);

namespace App\Filament\Widgets;

use App\Support\PlatformMetrics;
use Filament\Widgets\StatsOverviewWidget;
use Filament\Widgets\StatsOverviewWidget\Stat;

/**
 * Ключевые показатели за 30 дней.
 *
 * Показывается прирост, а не общий счётчик: «всего компаний» растёт
 * всегда и ни о чём не говорит, а «сколько пришло за месяц против
 * прошлого» — это уже основание для решения.
 */
class PlatformStats extends StatsOverviewWidget
{
    protected ?string $heading = 'За последние 30 дней';

    protected static ?int $sort = 1;

    protected function getStats(): array
    {
        $metrics = new PlatformMetrics;
        $summary = $metrics->summary();

        return [
            $this->stat('Новых компаний', $summary['companies'], 'heroicon-o-building-office'),
            $this->stat('Новых объявлений', $summary['listings'], 'heroicon-o-rectangle-stack'),
            $this->stat('Раскрытий контактов', $summary['unlocks'], 'heroicon-o-eye')
                ->description('Конверсия из просмотра: '.$metrics->unlockConversion().' %'),
            $this->stat('Выручка, сум', $summary['revenue'], 'heroicon-o-banknotes')
                ->description('Средний чек: '.number_format($metrics->averagePayment(), 0, ',', ' ').' сум'),
        ];
    }

    /** @param array{value: int|float, delta: float|null, suffix: string} $data */
    private function stat(string $label, array $data, string $icon): Stat
    {
        $value = number_format((float) $data['value'], 0, ',', ' ');
        $delta = $data['delta'];

        $stat = Stat::make($label, $value)->icon($icon);

        // Без прошлого периода сравнение невозможно — говорим прямо,
        // вместо «+100 %», которое читается как рост
        if ($delta === null) {
            return $stat->description('нет данных за прошлый период')->color('gray');
        }

        return $stat
            ->description(($delta > 0 ? '+' : '').$delta.' % к прошлым 30 дням')
            ->descriptionIcon($delta >= 0 ? 'heroicon-m-arrow-trending-up' : 'heroicon-m-arrow-trending-down')
            ->color($delta > 0 ? 'success' : ($delta < 0 ? 'danger' : 'gray'));
    }
}
