<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\Listing;
use App\Models\ListingStat;
use App\Models\SearchHit;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Request;

/**
 * Запись статистики: показы в выдаче, просмотры карточек, поисковые
 * запросы.
 *
 * Пишет сразу в двух местах: денормализованный счётчик на объявлении
 * (для списков, где нужна одна цифра без join) и строку по дню
 * в listing_stats (для графиков и сравнения периодов). Одно без
 * другого не работает: из счётчика не построить динамику, а из
 * ежедневных строк не получить итог без агрегата на каждый показ.
 */
class StatsRecorder
{
    /**
     * Сколько один посетитель не засчитывается повторно.
     *
     * Тридцать минут — компромисс: человек, вернувшийся к объявлению
     * через час, действительно посмотрел его второй раз, а обновление
     * страницы и переход «назад» не должны становиться просмотрами.
     */
    private const DEDUP_MINUTES = 30;

    /**
     * Показы в выдаче: объявления, попавшие в список результатов.
     *
     * @param  list<int>  $listingIds
     */
    public function impressions(array $listingIds): void
    {
        $listingIds = $this->withoutRecent($listingIds, 'imp');

        if ($listingIds === []) {
            return;
        }

        Listing::query()->whereIn('id', $listingIds)->increment('impressions_count');

        $this->bumpDaily($listingIds, 'impressions');
    }

    /** Просмотр карточки объявления. */
    public function view(Listing $listing): void
    {
        if ($this->withoutRecent([$listing->id], 'view') === []) {
            return;
        }

        $listing->increment('views_count');

        $this->bumpDaily([$listing->id], 'views');
    }

    public function favorite(Listing $listing): void
    {
        $listing->increment('favorites_count');

        $this->bumpDaily([$listing->id], 'favorites');
    }

    /** Раскрытие контакта — событие оплаченное, дедупликации не подлежит. */
    public function unlock(Listing $listing): void
    {
        $listing->increment('unlocks_count');

        $this->bumpDaily([$listing->id], 'unlocks');
    }

    /**
     * Поисковый запрос: показы и переходы по нему.
     *
     * Запрос нормализуется — «Цемент М400» и «цемент м400» это один
     * и тот же запрос, и в отчёте они должны стоять одной строкой.
     *
     * @param  list<int>  $companyIds
     */
    public function search(array $companyIds, string $query, int $impressions = 1): void
    {
        $normalized = mb_strtolower(trim(preg_replace('/\s+/u', ' ', $query) ?? ''));

        if ($normalized === '' || mb_strlen($normalized) > 190 || $companyIds === []) {
            return;
        }

        /*
         * Дата — строкой во всех запросах сразу.
         *
         * insertOrIgnore пишет мимо кастов модели и кладёт «2026-08-02»,
         * а where() с объектом Carbon подставляет «2026-08-02 00:00:00»
         * и ничего не находит. Инкремент тогда молча уходит в никуда.
         */
        $today = Carbon::today()->toDateString();
        $now = now();

        /*
         * Одной вставкой на весь список компаний. Раньше здесь стоял
         * цикл с firstOrCreate: страница поиска на двадцать объявлений
         * давала двадцать пар «выборка + вставка» на каждый заход
         * анонимного посетителя.
         */
        SearchHit::query()->insertOrIgnore(array_map(
            fn (int $companyId): array => [
                'company_id' => $companyId,
                'query' => $normalized,
                'date' => $today,
                'impressions' => 0,
                'clicks' => 0,
                'created_at' => $now,
                'updated_at' => $now,
            ],
            array_values(array_unique($companyIds)),
        ));

        SearchHit::query()
            ->whereIn('company_id', $companyIds)
            ->where('query', $normalized)
            ->where('date', $today)
            ->increment('impressions', $impressions);
    }

    /** Переход по результату поиска. */
    public function searchClick(int $companyId, string $query): void
    {
        $normalized = mb_strtolower(trim(preg_replace('/\s+/u', ' ', $query) ?? ''));

        if ($normalized === '') {
            return;
        }

        SearchHit::query()
            ->where('company_id', $companyId)
            ->where('query', $normalized)
            ->where('date', Carbon::today()->toDateString())
            ->increment('clicks');
    }

    /**
     * Отсеивает то, что этот же посетитель уже засчитал недавно.
     *
     * Ключ строится из сессии: она есть и у анонимного посетителя,
     * а IP делил бы на одного всех за общим NAT. Полностью накрутку
     * это не исключает — очистка кук её обходит, — но убирает
     * обновление страницы и переход «назад», из которых накрутка
     * и состояла на практике.
     *
     * @param  list<int>  $ids
     * @return list<int>
     */
    private function withoutRecent(array $ids, string $kind): array
    {
        if ($ids === [] || ! Request::hasSession()) {
            return $ids;
        }

        $visitor = Request::session()->getId();

        return array_values(array_filter($ids, function (int $id) use ($kind, $visitor): bool {
            $key = "stats:{$kind}:{$visitor}:{$id}";

            // add() ставит значение, только если ключа ещё нет —
            // ровно проверка «не считали ли мы это недавно»
            return cache()->add($key, true, now()->addMinutes(self::DEDUP_MINUTES));
        }));
    }

    /**
     * Инкремент дневных строк статистики.
     *
     * insertOrIgnore на весь список, затем один инкремент: цикл
     * firstOrCreate давал по паре запросов на каждое объявление,
     * то есть до сорока запросов на один показ страницы каталога.
     *
     * @param  list<int>  $listingIds
     */
    private function bumpDaily(array $listingIds, string $column): void
    {
        // Дата строкой — см. пояснение в search()
        $today = Carbon::today()->toDateString();
        $now = now();

        DB::transaction(function () use ($listingIds, $column, $today, $now): void {
            ListingStat::query()->insertOrIgnore(array_map(
                fn (int $id): array => [
                    'listing_id' => $id,
                    'date' => $today,
                    'impressions' => 0,
                    'views' => 0,
                    'favorites' => 0,
                    'unlocks' => 0,
                    'created_at' => $now,
                    'updated_at' => $now,
                ],
                $listingIds,
            ));

            ListingStat::query()
                ->whereIn('listing_id', $listingIds)
                ->where('date', $today)
                ->increment($column);
        });
    }
}
