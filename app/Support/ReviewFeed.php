<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\Company;
use App\Models\PlatformReview;
use App\Models\Review;
use Illuminate\Database\Query\Builder;
use Illuminate\Support\Facades\DB;

/**
 * Лента опубликованных отзывов: о компаниях и о самой площадке.
 *
 * Одна лента на главную (три свежих) и на страницу «Все отзывы».
 * Порядок собирается одним запросом UNION по дате, а не склейкой двух
 * списков в памяти: иначе постраничный вывод пропускал бы и повторял
 * отзывы на стыке страниц. Тот же запрос повторяет Django
 * (python/savdex/web/reviews.py) — страницы отдаёт он.
 *
 * Отзыв о компании попадает в ленту по тем же правилам, что и раньше
 * на главной: опубликован, компания жива и не заблокирована, автор
 * не удалён. Сочинённых отзывов здесь нет и быть не может — источник
 * только таблицы, куда пишут сами пользователи.
 */
final class ReviewFeed
{
    public const TYPES = ['all', 'platform', 'company'];

    public const PER_PAGE = 20;

    private static function companyRows(): Builder
    {
        return DB::table('reviews as r')
            ->join('companies as c', 'c.id', '=', 'r.company_id')
            ->join('companies as a', 'a.id', '=', 'r.author_company_id')
            ->where('r.status', Review::STATUS_PUBLISHED)
            ->where('c.status', Company::STATUS_ACTIVE)
            ->whereNull('c.deleted_at')
            ->whereNull('a.deleted_at')
            ->selectRaw("'company' as kind, r.id, r.created_at");
    }

    private static function platformRows(): Builder
    {
        return DB::table('platform_reviews as p')
            ->where('p.status', PlatformReview::STATUS_PUBLISHED)
            ->selectRaw("'platform' as kind, p.id, p.created_at");
    }

    private static function rows(string $type): Builder
    {
        return match ($type) {
            'platform' => self::platformRows(),
            'company' => self::companyRows(),
            default => self::companyRows()->unionAll(self::platformRows()),
        };
    }

    public static function count(string $type): int
    {
        return (int) DB::query()->fromSub(self::rows($type), 'feed')->count();
    }

    /**
     * Отзывы ленты по порядку: свежие сверху.
     *
     * @return list<array<string, mixed>>
     */
    public static function take(string $type, int $limit, int $offset = 0): array
    {
        $rows = DB::query()
            ->fromSub(self::rows($type), 'feed')
            ->orderByDesc('created_at')
            ->orderBy('kind')
            ->orderByDesc('id')
            ->limit($limit)
            ->offset($offset)
            ->get();

        $ids = fn (string $kind): array => $rows->where('kind', $kind)->pluck('id')->all();

        $company = Review::query()
            ->with(['company:id,slug,name', 'authorCompany:id,name'])
            ->whereIn('id', $ids('company'))
            ->get()
            ->keyBy('id');

        $platform = PlatformReview::query()
            ->with(['user:id,name', 'company:id,name'])
            ->whereIn('id', $ids('platform'))
            ->get()
            ->keyBy('id');

        $translations = app(ContentTranslation::class);
        $translations->prefetch(
            $company->pluck('body')->merge($platform->pluck('body'))->all(),
            app()->getLocale(),
        );

        return $rows->map(fn (object $row): array => $row->kind === 'company'
            ? self::companyCard($company[$row->id])
            : self::platformCard($platform[$row->id])
        )->all();
    }

    /** @return array<string, mixed> */
    private static function companyCard(Review $r): array
    {
        return [
            'id' => $r->id,
            'kind' => 'company',
            'author' => $r->authorCompany->name,
            'initials' => $r->authorCompany->initials(),
            'rating' => (int) $r->rating,
            'body' => ContentTranslation::text($r->body),
            'when' => $r->created_at->translatedFormat('d.m.Y'),
            'company_name' => $r->company->name,
            'company_slug' => $r->company->slug,
        ];
    }

    /** @return array<string, mixed> */
    private static function platformCard(PlatformReview $r): array
    {
        $author = self::platformAuthor($r);

        return [
            'id' => $r->id,
            'kind' => 'platform',
            'author' => $author,
            'initials' => Company::initialsOf($author),
            'rating' => (int) $r->rating,
            'body' => ContentTranslation::text($r->body),
            'when' => $r->created_at->translatedFormat('d.m.Y'),
            'company_name' => null,
            'company_slug' => null,
        ];
    }

    /**
     * Подпись автора отзыва о площадке.
     *
     * Компания — её название: так подписаны и отзывы о компаниях
     * (удалённая компания не подгружается — тогда как без неё).
     * Без компании — имя и первая буква фамилии: полное имя частного
     * человека на публичной странице ни к чему.
     */
    private static function platformAuthor(PlatformReview $r): string
    {
        if ($r->company !== null) {
            return $r->company->name;
        }

        $words = preg_split('/\s+/u', trim((string) $r->user?->name), -1, PREG_SPLIT_NO_EMPTY) ?: [];

        if ($words === []) {
            return __('ui.platform_reviews.anonymous');
        }

        return count($words) === 1
            ? $words[0]
            : $words[0].' '.mb_strtoupper(mb_substr($words[1], 0, 1)).'.';
    }

    /**
     * Сводка по отзывам о площадке: средняя, число, разбивка по звёздам
     * и средние по сторонам работы. Округление — в базе: Django берёт
     * те же числа тем же запросом.
     *
     * @return array<string, mixed>
     */
    public static function platformSummary(): array
    {
        $published = fn () => DB::table('platform_reviews')->where('status', PlatformReview::STATUS_PUBLISHED);

        $row = $published()
            ->selectRaw('count(*) as total, round(avg(rating), 1) as average')
            ->first();

        $stars = $published()
            ->selectRaw('rating, count(*) as total')
            ->groupBy('rating')
            ->pluck('total', 'rating');

        $criteria = [];

        foreach (PlatformReview::criteriaLabels() as $field => $label) {
            $average = $published()->whereNotNull($field)->selectRaw("round(avg({$field}), 1) as average")->value('average');

            $criteria[] = [
                'key' => PlatformReview::CRITERIA[$field],
                'label' => $label,
                'average' => $average === null ? null : (float) $average,
            ];
        }

        return [
            'count' => (int) $row->total,
            'average' => $row->average === null ? null : (float) $row->average,
            'stars' => array_map(
                fn (int $star): array => ['star' => $star, 'count' => (int) ($stars[$star] ?? 0)],
                [5, 4, 3, 2, 1],
            ),
            'criteria' => $criteria,
        ];
    }
}
