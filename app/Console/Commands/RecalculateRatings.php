<?php

declare(strict_types=1);

namespace App\Console\Commands;

use App\Models\Company;
use App\Models\Review;
use Illuminate\Console\Command;
use Illuminate\Support\Facades\DB;

/**
 * Пересчёт рейтингов компаний.
 *
 * Рейтинг байесовский, а не среднее арифметическое (§5.6 FR-REV-06 ТЗ).
 * Простое среднее ставит компанию с одним отзывом на пять звёзд выше
 * компании с сотней отзывов и средним 4,8 — а это ровно та компания,
 * которой стоит доверять больше.
 *
 * Формула: (C × m + сумма оценок) / (C + число отзывов), где m —
 * средняя оценка по площадке, C — вес этого среднего (сколько
 * «виртуальных» отзывов подмешивается). При C = 5 компания с одним
 * отзывом почти не отличается от средней, с двадцатью — почти
 * полностью определяется своими оценками.
 */
class RecalculateRatings extends Command
{
    protected $signature = 'ratings:recalculate';

    protected $description = 'Пересчитать байесовские рейтинги компаний';

    /** Вес среднего по площадке. */
    private const WEIGHT = 5;

    public function handle(): int
    {
        $globalAverage = (float) Review::query()->where('status', 'published')->avg('rating');

        if ($globalAverage === 0.0) {
            // Отзывов нет вообще — исходим из нейтральной середины,
            // иначе первая же компания с отзывом получит рейтинг «5»
            $globalAverage = 4.0;
        }

        $stats = Review::query()
            ->where('status', 'published')
            ->select('company_id', DB::raw('COUNT(*) as total'), DB::raw('SUM(rating) as sum_rating'))
            ->groupBy('company_id')
            ->get()
            ->keyBy('company_id');

        $updated = 0;

        Company::query()->chunkById(200, function ($companies) use ($stats, $globalAverage, &$updated): void {
            foreach ($companies as $company) {
                $row = $stats->get($company->id);

                $count = (int) ($row->total ?? 0);
                $sum = (float) ($row->sum_rating ?? 0);

                $rating = $count > 0
                    ? (self::WEIGHT * $globalAverage + $sum) / (self::WEIGHT + $count)
                    : 0.0;

                $company->forceFill([
                    'rating' => round($rating, 2),
                    'reviews_count' => $count,
                ])->save();

                $updated++;
            }
        });

        $this->info("Пересчитано компаний: {$updated}. Среднее по площадке: ".round($globalAverage, 2));

        return self::SUCCESS;
    }
}
