<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\Tender;
use Illuminate\Support\Str;

/**
 * Карточка тендера для витрины.
 *
 * Одна форма данных на список в каталоге, блок похожих и страницу
 * самого тендера — как ListingCard у объявлений. Раньше она жила
 * приватным методом контроллера, и когда список тендеров переехал
 * в каталог, её понадобилось звать из двух контроллеров сразу.
 */
final class TenderCard
{
    /** @return array<string, mixed> */
    public static function present(Tender $tender): array
    {
        return [
            'id' => $tender->id,
            'slug' => $tender->slug,
            'title' => $tender->localizedTitle(),
            'excerpt' => Str::limit(trim((string) $tender->localizedDescription()), 180),
            'customer' => $tender->customer,
            'category' => $tender->category?->name(),
            'country' => $tender->country?->name(),
            'location' => $tender->location,
            'budget' => $tender->budget !== null ? (float) $tender->budget : null,
            'currency' => $tender->currency,
            'deadline' => DateHelper::dayMonthYear($tender->deadline_at),
            'days_left' => self::daysLeft($tender),
            'closed' => $tender->isClosed(),
            'published' => DateHelper::dayMonthYear($tender->published_at),
        ];
    }

    /**
     * Связи, которые нужно жадно загрузить перед present().
     *
     * @return list<string>
     */
    public static function relations(): array
    {
        return ['category.translations', 'country.translations'];
    }

    /** Дней до конца приёма заявок; null — срок не указан. */
    private static function daysLeft(Tender $tender): ?int
    {
        if ($tender->deadline_at === null) {
            return null;
        }

        return (int) now()->startOfDay()->diffInDays($tender->deadline_at->copy()->startOfDay(), false);
    }
}
