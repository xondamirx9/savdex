<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\Company;
use App\Models\ListingStat;
use Illuminate\Support\Carbon;
use Illuminate\Support\Collection;

/**
 * Показатели компании за период.
 *
 * Считаются по таблице listing_stats, а не по счётчикам объявления:
 * счётчик знает только «сколько всего», а кабинету нужно «сколько
 * за 30 дней и как это соотносится с предыдущими 30».
 */
class CabinetMetrics
{
    public function __construct(
        private readonly Company $company,
        private readonly int $days = 30,
    ) {}

    /**
     * Сводка с изменением к предыдущему периоду того же размера.
     *
     * @return array<string, array{value: float|int, delta: float|null, format: string}>
     */
    public function summary(): array
    {
        $now = $this->sum($this->from(), $this->to());
        $prev = $this->sum($this->from()->copy()->subDays($this->days), $this->from());

        $conversion = fn (array $p): float => $p['views'] > 0 ? round($p['unlocks'] / $p['views'] * 100, 1) : 0.0;

        return [
            'impressions' => [
                'value' => $now['impressions'],
                'delta' => $this->delta($now['impressions'], $prev['impressions']),
                'format' => 'int',
            ],
            'views' => [
                'value' => $now['views'],
                'delta' => $this->delta($now['views'], $prev['views']),
                'format' => 'int',
            ],
            'unlocks' => [
                'value' => $now['unlocks'],
                'delta' => $this->delta($now['unlocks'], $prev['unlocks']),
                'format' => 'int',
            ],
            'conversion' => [
                'value' => $conversion($now),
                // Конверсия — уже процент, поэтому разница в пунктах,
                // а не в процентах от процента
                'delta' => round($conversion($now) - $conversion($prev), 1),
                'format' => 'percent',
            ],
        ];
    }

    /**
     * Ряд значений по дням для спарклайна.
     *
     * Значения сглаживаются скользящим средним по неделе. Без сглаживания
     * спад на выходных превращает график в пилу во всю высоту: спарклайн
     * масштабируется от минимума к максимуму, и недельная волна забивает
     * тренд, ради которого график и рисуется.
     *
     * @return array<string, list<float>>
     */
    public function series(): array
    {
        $rows = $this->rows($this->from(), $this->to())->keyBy(fn ($r) => $r->date->toDateString());

        $raw = ['impressions' => [], 'views' => [], 'unlocks' => []];

        for ($i = $this->days - 1; $i >= 0; $i--) {
            $key = Carbon::today()->subDays($i)->toDateString();
            $row = $rows->get($key);

            foreach ($raw as $metric => $_) {
                $raw[$metric][] = (int) ($row->{$metric} ?? 0);
            }
        }

        return array_map($this->smooth(...), $raw);
    }

    /**
     * Скользящее среднее по семи дням.
     *
     * Окно неполное в начале ряда — берём столько дней, сколько есть:
     * обрезать первые шесть точек значит потерять начало периода.
     *
     * @param  list<int>  $values
     * @return list<float>
     */
    private function smooth(array $values, int $window = 7): array
    {
        $out = [];

        foreach ($values as $i => $_) {
            $slice = array_slice($values, max(0, $i - $window + 1), min($i + 1, $window));
            $out[] = round(array_sum($slice) / count($slice), 1);
        }

        return $out;
    }

    /**
     * Воронка: показы → просмотры → избранное → контакты → отзывы.
     *
     * @return list<array{label: string, value: int, share: float, tone: string}>
     */
    public function funnel(): array
    {
        $totals = $this->sum($this->from(), $this->to());
        $reviews = $this->company->reviews()->where('created_at', '>=', $this->from())->count();

        $top = max(1, $totals['impressions']);

        $steps = [
            ['Показы в выдаче', $totals['impressions'], 'primary'],
            ['Просмотры карточки', $totals['views'], 'primary'],
            ['Добавили в избранное', $totals['favorites'], 'primary'],
            ['Открыли контакт', $totals['unlocks'], 'success'],
            ['Оставили отзыв', $reviews, 'warning'],
        ];

        return array_map(fn (array $s): array => [
            'label' => $s[0],
            'value' => $s[1],
            'share' => round($s[1] / $top * 100, 1),
            'tone' => $s[2],
        ], $steps);
    }

    /**
     * Города, из которых приходили просмотры.
     *
     * Пока источник — города компаний, открывавших контакты: точная
     * геоаналитика требует событий просмотра с геометкой (спринт 9).
     *
     * @return list<array{label: string, value: int}>
     */
    public function geography(): array
    {
        return $this->company->unlockedBy()
            ->with('company.city.translations')
            ->get()
            ->groupBy(fn ($u) => $u->company?->city?->name() ?? 'Не указан')
            ->map->count()
            ->sortDesc()
            ->take(6)
            ->map(fn (int $count, string $label): array => ['label' => $label, 'value' => $count])
            ->values()
            ->all();
    }

    /**
     * Поисковые запросы с CTR.
     *
     * @return list<array{query: string, impressions: int, clicks: int, ctr: float}>
     */
    public function queries(int $limit = 10): array
    {
        return $this->company->searchHits()
            ->where('date', '>=', $this->from())
            ->selectRaw('query, SUM(impressions) as impressions, SUM(clicks) as clicks')
            ->groupBy('query')
            ->orderByDesc('impressions')
            ->limit($limit)
            ->get()
            ->map(fn ($h): array => [
                'query' => $h->query,
                'impressions' => (int) $h->impressions,
                'clicks' => (int) $h->clicks,
                'ctr' => $h->impressions > 0 ? round($h->clicks / $h->impressions * 100, 1) : 0.0,
            ])
            ->all();
    }

    private function from(): Carbon
    {
        return Carbon::today()->subDays($this->days - 1);
    }

    private function to(): Carbon
    {
        return Carbon::today();
    }

    /** @return Collection<int, ListingStat> */
    private function rows(Carbon $from, Carbon $to): Collection
    {
        return ListingStat::query()
            ->whereIn('listing_id', $this->company->listings()->select('id'))
            ->whereBetween('date', [$from, $to])
            ->selectRaw('date, SUM(impressions) as impressions, SUM(views) as views, SUM(favorites) as favorites, SUM(unlocks) as unlocks')
            ->groupBy('date')
            ->get();
    }

    /** @return array{impressions: int, views: int, favorites: int, unlocks: int} */
    private function sum(Carbon $from, Carbon $to): array
    {
        $rows = $this->rows($from, $to);

        return [
            'impressions' => (int) $rows->sum('impressions'),
            'views' => (int) $rows->sum('views'),
            'favorites' => (int) $rows->sum('favorites'),
            'unlocks' => (int) $rows->sum('unlocks'),
        ];
    }

    /**
     * Изменение в процентах.
     * null, когда сравнивать не с чем: «+100 %» от нуля — неправда.
     */
    private function delta(int $now, int $prev): ?float
    {
        return $prev > 0 ? round(($now - $prev) / $prev * 100, 1) : null;
    }
}
