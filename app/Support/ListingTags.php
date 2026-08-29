<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\Listing;

/**
 * Теги объявления — автоматически, из его же данных.
 *
 * Ничего не хранится: набор детерминированно выводится из заголовка,
 * категории, характеристик и города, поэтому теги есть у всякого
 * объявления сразу — включая опубликованные до появления функции —
 * и не разъезжаются с содержимым после правки.
 *
 * Клик по тегу ведёт в поиск каталога, и слова берутся только те,
 * по которым поиск это объявление найдёт: из его собственного текста
 * и справочных полей.
 */
class ListingTags
{
    /** Больше — уже облако мусора, а не подсказка. */
    private const MAX_TAGS = 8;

    /** Сколько значащих слов берётся из заголовка. */
    private const TITLE_WORDS = 5;

    /**
     * Служебные слова заголовков: намерение, упаковка, предлоги.
     * Тег #куплю не говорит о товаре ничего.
     */
    private const STOP_WORDS = [
        'куплю', 'продам', 'продаю', 'купим', 'продаём', 'ищем', 'ищу',
        'опт', 'оптом', 'розница', 'шт', 'штук', 'тонн', 'тонны', 'кг',
        'для', 'под', 'из', 'на', 'в', 'с', 'со', 'по', 'от', 'до', 'и',
        'или', 'без', 'при', 'за', 'это', 'как', 'все', 'любой', 'любые',
        'sotib', 'olamiz', 'sotamiz', 'dona', 'uchun',
    ];

    /** Сколько вариантов предлагается владельцу на выбор. */
    private const MAX_SUGGESTIONS = 12;

    /**
     * Теги для показа на витрине.
     *
     * Выбор владельца в приоритете, но только та его часть, что
     * до сих пор входит в предлагаемый список: после правки заголовка
     * устаревший выбор отпадает сам. Без выбора — автонабор.
     *
     * @return list<string>
     */
    public static function for(Listing $listing): array
    {
        $chosen = array_values(array_intersect(
            array_map(strval(...), (array) $listing->tags),
            self::suggestions($listing),
        ));

        if ($chosen !== []) {
            return array_slice($chosen, 0, self::MAX_TAGS);
        }

        return array_slice(self::suggestions($listing), 0, self::MAX_TAGS);
    }

    /**
     * Список, из которого владелец выбирает. Только предложенное:
     * произвольный текст в теги не попадает ни при каком вводе.
     *
     * @return list<string>
     */
    public static function suggestions(Listing $listing): array
    {
        $tags = [];

        // Категория и её раздел — самые точные «что это»
        foreach ([$listing->category, $listing->category?->parent] as $category) {
            if ($category !== null) {
                $tags[] = mb_strtolower($category->name());
            }
        }

        // Значащие слова заголовка: товар обычно стоит первым
        $clean = preg_replace('/[^\p{L}\p{N}\s×xх-]+/u', ' ', mb_strtolower((string) $listing->title)) ?? '';

        $words = collect(preg_split('/\s+/u', $clean, flags: PREG_SPLIT_NO_EMPTY) ?: [])
            ->filter(fn (string $w): bool => mb_strlen($w) >= 3
                && ! in_array($w, self::STOP_WORDS, true)
                && preg_match('/\p{L}/u', $w) === 1)
            ->take(self::TITLE_WORDS);

        $tags = [...$tags, ...$words];

        // Характеристики-размеры узнаваемы и различают похожие позиции
        foreach ($listing->attributes as $attribute) {
            $value = trim((string) $attribute->value);

            if ($value !== '' && mb_strlen($value) <= 20 && preg_match('/\d/', $value) === 1) {
                $tags[] = mb_strtolower($value);
            }
        }

        $city = $listing->company?->city?->name();

        if ($city !== null && $city !== '') {
            $tags[] = mb_strtolower($city);
        }

        return collect($tags)
            ->map(fn (string $t): string => trim($t))
            ->filter(fn (string $t): bool => $t !== '')
            ->unique()
            ->take(self::MAX_SUGGESTIONS)
            ->values()
            ->all();
    }
}
