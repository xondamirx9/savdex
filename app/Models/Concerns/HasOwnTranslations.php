<?php

declare(strict_types=1);

namespace App\Models\Concerns;

use App\Support\ContentTranslation;

/**
 * Текст со своими полями под языки и машинным переводом про запас.
 *
 * Русский — в основном столбце, остальные языки — в столбце *_i18n
 * ({"uz": "...", "en": "..."}), и их заполняет администратор. Язык,
 * который не заполнили, сайт показывает машинным переводом русского
 * текста (App\Support\ContentTranslation): лучше перевод, чем русский
 * абзац посреди узбекской страницы.
 */
trait HasOwnTranslations
{
    /** Текст, вписанный для языка администратором; пусто — не вписан. */
    public function own(string $field, ?string $locale = null): string
    {
        $locale ??= app()->getLocale();

        if ($locale === 'ru') {
            return trim((string) $this->getAttribute($field));
        }

        $i18n = $this->getAttribute($field.'_i18n');

        return is_array($i18n) ? trim((string) ($i18n[$locale] ?? '')) : '';
    }

    /** Свой текст на языке посетителя, иначе машинный перевод русского. */
    public function localized(string $field, ?string $locale = null): string
    {
        $locale ??= app()->getLocale();
        $own = $this->own($field, $locale);

        if ($own !== '' || $locale === 'ru') {
            return $own;
        }

        return trim((string) ContentTranslation::text($this->getAttribute($field), $locale));
    }
}
