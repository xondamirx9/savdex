<?php

declare(strict_types=1);

namespace App\Http\Controllers\Cabinet;

use App\Http\Controllers\Controller;
use App\Support\CabinetMetrics;
use Illuminate\Http\Request;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Аналитика компании.
 *
 * Расширенная часть — бенчмарк по категории и запросы — входит
 * в Business и Premium. На младших тарифах показываются базовые
 * показатели и воронка: без них человек не поймёт, за что доплачивать.
 */
class AnalyticsController extends Controller
{
    private const PERIODS = [7, 30, 90];

    /**
     * Подписи периодов на языке сайта.
     *
     * Метод, а не константа: константа вычисляется один раз при
     * загрузке класса, и выбранный тогда язык застыл бы в ней до
     * перезапуска процесса.
     *
     * @return array<int, string>
     */
    private static function periods(): array
    {
        return array_combine(
            self::PERIODS,
            array_map(fn (int $days): string => __('ui.cabinet.analytics.period_days', ['days' => $days]), self::PERIODS),
        );
    }

    public function index(Request $request): Response
    {
        $company = $request->user()->company;

        if ($company === null) {
            return Inertia::render('cabinet/Analytics', [
                'metrics' => null,
                'funnel' => [],
                'geography' => [],
                'queries' => [],
                'benchmark' => [],
                'periods' => self::periods(),
                'period' => 30,
                'advanced' => false,
                'plan' => null,
            ]);
        }

        $period = (int) $request->integer('period', 30);

        if (! in_array($period, self::PERIODS, true)) {
            $period = 30;
        }

        $plan = $company->plan();
        $metrics = new CabinetMetrics($company, $period);
        $summary = $metrics->summary();

        return Inertia::render('cabinet/Analytics', [
            'metrics' => $summary,
            'series' => $metrics->series(),
            'funnel' => $metrics->funnel(),
            'geography' => $metrics->geography(),
            'queries' => $plan->advanced_analytics ? $metrics->queries() : [],
            'benchmark' => $plan->advanced_analytics ? $this->benchmark($summary) : [],
            'periods' => self::periods(),
            'period' => $period,
            'advanced' => (bool) $plan->advanced_analytics,
            'plan' => ['name' => $plan->name],
        ]);
    }

    /**
     * Сравнение с категорией.
     *
     * Медиана пока задана константой: считать её по площадке можно
     * только на достаточном числе компаний в категории, иначе «медиана»
     * — это показатели одного-двух участников, и сравнение обманывает.
     * Как только категории наполнятся, значение начнёт считаться (спринт 9).
     *
     * @param  array<string, array{value: float|int, delta: float|null, format: string}>  $summary
     * @return list<array{label: string, you: float, median: float, position: float, verdict: string, tone: string}>
     */
    private function benchmark(array $summary): array
    {
        $views = (float) $summary['views']['value'];
        $impressions = max(1.0, (float) $summary['impressions']['value']);
        $ctr = round($views / $impressions * 100, 1);
        $conversion = (float) $summary['conversion']['value'];

        return [
            $this->row(__('ui.cabinet.analytics.ctr'), $ctr, 12.0),
            $this->row(__('ui.cabinet.analytics.to_contact'), $conversion, 4.0),
        ];
    }

    /** @return array{label: string, you: float, median: float, verdict: string, tone: string} */
    private function row(string $label, float $you, float $median): array
    {
        $ratio = $median > 0 ? $you / $median : 1.0;

        [$verdict, $tone] = match (true) {
            $ratio >= 1.4 => [__('ui.cabinet.analytics.top_quarter'), 'success'],
            $ratio >= 1.0 => [__('ui.cabinet.analytics.above_median'), 'success'],
            $ratio >= 0.7 => [__('ui.cabinet.analytics.near_median'), 'muted'],
            default => [__('ui.cabinet.analytics.below_median'), 'warning'],
        };

        return [
            'label' => $label,
            'you' => $you,
            'median' => $median,
            // Положение отметки на шкале: медиана всегда в середине,
            // чтобы отклонение читалось без чтения чисел
            'position' => min(96.0, max(4.0, $ratio * 50)),
            'verdict' => $verdict,
            'tone' => $tone,
        ];
    }
}
