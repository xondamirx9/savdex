<?php

declare(strict_types=1);

namespace App\Models;

use App\Models\Concerns\HasOwnTranslations;
use App\Support\ContentTranslation;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;

/**
 * Секция главной страницы: тексты и видимость (§6.5 ТЗ).
 *
 * Решение заказчика: из админки правятся тексты, вопросы и видимость
 * секций, а порядок остаётся таким, как в макете, — у каждой секции
 * своя вёрстка, и переставленная секция ломала бы композицию страницы.
 * Поэтому набор блоков задан кодом (KEYS), раздел админки на Python
 * (python/savdex/site/landing_admin.py) блоки не заводит и не удаляет.
 *
 * Языки — свои поля и машинный перевод про запас (HasOwnTranslations).
 * У «Как это работает» и «Частых вопросов» пункты — в body: название
 * первой строкой, пояснение следующей, пункты через пустую строку.
 * У призыва в конце body — подпись под кнопкой.
 */
#[Fillable([
    'key', 'name', 'eyebrow', 'eyebrow_i18n', 'heading', 'heading_i18n',
    'subheading', 'subheading_i18n', 'button', 'button_i18n', 'body', 'body_i18n',
    'payload', 'is_visible', 'sort',
])]
class LandingBlock extends Model
{
    use HasOwnTranslations;

    /** Секции главной в порядке макета. */
    public const KEYS = [
        'hero', 'stats', 'categories', 'vip', 'products', 'requests', 'suppliers',
        'how', 'reviews', 'faq', 'news', 'cta',
    ];

    /** Секции, у которых текст — пункты. */
    public const WITH_ITEMS = ['how', 'faq'];

    protected function casts(): array
    {
        return [
            'payload' => 'array',
            'is_visible' => 'boolean',
            'eyebrow_i18n' => 'array',
            'heading_i18n' => 'array',
            'subheading_i18n' => 'array',
            'button_i18n' => 'array',
            'body_i18n' => 'array',
        ];
    }

    /**
     * Все секции главной на языке посетителя: ключ → тексты.
     *
     * Первый экран не скрывается: на нём поиск.
     *
     * @return array<string, array<string, mixed>>
     */
    public static function cards(): array
    {
        return self::query()
            ->whereIn('key', self::KEYS)
            ->get()
            ->mapWithKeys(fn (self $block): array => [$block->key => $block->card()])
            ->all();
    }

    /** @return array<string, mixed> */
    public function card(): array
    {
        $card = [
            'visible' => $this->is_visible || $this->key === 'hero',
            'eyebrow' => $this->localized('eyebrow'),
            'heading' => $this->localized('heading'),
            'subheading' => $this->localized('subheading'),
            'button' => $this->localized('button'),
        ];

        if (in_array($this->key, self::WITH_ITEMS, true)) {
            $card['items'] = $this->items();
        } else {
            $card['note'] = $this->localized('body');
        }

        return $card;
    }

    /**
     * Пункты секции: название и пояснение.
     *
     * Свой текст языка — как есть; не вписан — пункты берутся из
     * русского текста и переводятся по одному: целиком переводчик мог
     * бы склеить или разорвать пункты.
     *
     * @return list<array{title: string, text: string}>
     */
    public function items(?string $locale = null): array
    {
        $locale ??= app()->getLocale();
        $own = $this->own('body', $locale);

        if ($own !== '' || $locale === 'ru') {
            return self::parseItems($own);
        }

        $items = self::parseItems($this->body);
        app(ContentTranslation::class)->prefetch(
            array_merge(...array_map(fn (array $item): array => array_values($item), $items ?: [[]])),
            $locale,
        );

        return array_map(fn (array $item): array => [
            'title' => (string) ContentTranslation::text($item['title'], $locale),
            'text' => (string) ContentTranslation::text($item['text'], $locale),
        ], $items);
    }

    /** @return list<array{title: string, text: string}> */
    public static function parseItems(?string $text): array
    {
        $items = [];

        foreach (preg_split('/\R\s*\R/u', trim((string) $text)) ?: [] as $chunk) {
            $lines = array_values(array_filter(
                array_map('trim', preg_split('/\R/u', trim($chunk)) ?: []),
                fn (string $line): bool => $line !== '',
            ));

            if ($lines !== []) {
                $items[] = ['title' => $lines[0], 'text' => implode(' ', array_slice($lines, 1))];
            }
        }

        return $items;
    }
}
