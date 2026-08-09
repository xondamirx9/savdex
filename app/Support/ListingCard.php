<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\Listing;

/**
 * Карточка объявления для витрины.
 *
 * Одна форма данных на все списки — каталог, главную, избранное,
 * похожие объявления. Раньше каждый контроллер собирал массив сам,
 * и наборы полей расходились: карточка на главной не знала минимальную
 * партию, а в каталоге не было страны поставщика.
 */
final class ListingCard
{
    /** Сколько дней объявление считается новым для метки «NEW». */
    private const NEW_DAYS = 7;

    /** @return array<string, mixed> */
    public static function present(Listing $listing): array
    {
        return [
            'id' => $listing->id,
            'slug' => $listing->slug,
            'title' => $listing->title,
            'excerpt' => str($listing->description ?? '')->limit(140)->toString(),
            'type' => $listing->type,
            'category' => $listing->category?->name(),
            'price' => $listing->price !== null ? (float) $listing->price : null,
            'currency' => $listing->currency,
            'unit' => $listing->unit,
            'negotiable' => $listing->price_negotiable,
            'min_order' => $listing->min_order,
            'city' => $listing->company?->city?->name(),
            // Страна поставщика: на карточке она отображается флагом
            'country' => $listing->company?->country?->code,
            'country_name' => $listing->company?->country?->name(),
            'published' => $listing->published_at?->diffForHumans(),
            'is_new' => $listing->published_at !== null
                && $listing->published_at->gt(now()->subDays(self::NEW_DAYS)),
            'views' => $listing->views_count,
            // Обложка — первая фотография; её отсутствие карточка
            // рисует плашкой, а не пустым местом
            'cover' => $listing->images->first()?->thumbUrl(),
            'photos' => $listing->images->count(),
            'company' => [
                'name' => $listing->company?->name,
                'slug' => $listing->company?->slug,
                'verified' => (int) ($listing->company?->verification_level ?? 0),
                'rating' => (float) ($listing->company?->rating ?? 0),
            ],
            // Метки продвижения показываются как есть: скрывать факт
            // платного размещения площадка не будет
            'badges' => $listing->activePromotions
                ->map(fn ($p): ?string => $p->type?->badge)
                ->filter()
                ->values(),
            'promoted' => $listing->activePromotions->isNotEmpty(),
        ];
    }

    /**
     * Связи, которые нужно жадно загрузить перед present():
     * без списка каждый вызывающий собирал бы его сам и что-то забывал.
     *
     * @return list<string>
     */
    public static function relations(): array
    {
        return [
            'company:id,name,slug,verification_level,rating,city_id,country_id',
            'company.city.translations',
            'company.country.translations',
            'category.translations',
            'activePromotions.type',
            'images',
        ];
    }
}
