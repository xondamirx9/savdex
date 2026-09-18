<?php

declare(strict_types=1);

use App\Models\Company;
use App\Models\Review;
use App\Services\ReviewService;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Один отзыв компании о компании — теперь и на стороне базы.
 *
 * Индекс reviews_unique_per_deal на (компания, автор, объявление)
 * обещал это с самого начала, но обещания не держал: у отзыва о работе
 * с компанией вообще объявления нет, а NULL в уникальном индексе не
 * равен NULL — ни в PostgreSQL, ни в SQLite. То есть на единственном
 * виде отзывов, который вообще создаёт витрина, индекс не срабатывал:
 * перехват UniqueConstraintViolationException в ReviewService (защита
 * от двойного нажатия) не мог сработать ни разу.
 *
 * Частичный индекс закрывает ровно этот случай. Дубликаты, если они
 * успели появиться, разбираются до создания индекса: остаётся самый
 * ранний отзыв пары — тот, который писал живой человек, — а рейтинг
 * компании пересчитывается, потому что лишние оценки в него попали.
 */
return new class extends Migration
{
    private const INDEX = 'reviews_unique_per_company';

    public function up(): void
    {
        $this->removeDuplicates();

        DB::statement(
            'create unique index '.self::INDEX.' on reviews (company_id, author_company_id) where listing_id is null',
        );
    }

    public function down(): void
    {
        DB::statement('drop index if exists '.self::INDEX);
    }

    /** Из каждой пары остаётся самый ранний отзыв. */
    private function removeDuplicates(): void
    {
        $pairs = DB::table('reviews')
            ->selectRaw('company_id, author_company_id, count(*) as total')
            ->whereNull('listing_id')
            ->groupBy('company_id', 'author_company_id')
            ->havingRaw('count(*) > 1')
            ->get();

        foreach ($pairs as $pair) {
            $extra = Review::query()
                ->where('company_id', $pair->company_id)
                ->where('author_company_id', $pair->author_company_id)
                ->whereNull('listing_id')
                ->orderBy('id')
                ->skip(1)
                ->take(1000)
                ->get();

            foreach ($extra as $review) {
                $review->delete();
            }
        }

        // Пересчёт после удаления: лишние оценки уже успели попасть
        // в средний балл и в число отзывов на визитке
        if ($pairs->isNotEmpty()) {
            $service = app(ReviewService::class);

            foreach ($pairs->pluck('company_id')->unique() as $companyId) {
                $company = Company::query()->find($companyId);

                if ($company !== null) {
                    $service->recalculate($company);
                }
            }
        }
    }
};
