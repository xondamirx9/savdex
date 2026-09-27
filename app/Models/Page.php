<?php

declare(strict_types=1);

namespace App\Models;

use App\Models\Concerns\HasOwnTranslations;
use App\Support\ContentTranslation;
use App\Support\PageBody;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\HasMany;

/**
 * Страница сайта с текстом из админки: «О компании», «Контакты»,
 * «Помощь», «Инструкция», «Правила».
 *
 * Набор страниц задан кодом (KEYS): у каждой свой адрес и своя вёрстка,
 * а админка правит только текст. Раздел на Python (этап 2 переноса,
 * python/savdex/site/pages_admin.py) страницы не заводит и не удаляет.
 *
 * Текст — с разметкой App\Support\PageBody; языки — свои поля и
 * машинный перевод про запас (HasOwnTranslations).
 */
#[Fillable([
    'key', 'slug', 'title', 'title_i18n', 'excerpt', 'excerpt_i18n', 'body', 'body_i18n',
    'meta_title', 'meta_description', 'is_published', 'sort',
])]
class Page extends Model
{
    use HasOwnTranslations;

    /** Страницы со своим адресом; «О компании» и «Контакты» — /about. */
    public const DOCS = ['help', 'guide', 'rules'];

    public const KEYS = ['about', 'contacts', ...self::DOCS];

    protected function casts(): array
    {
        return [
            'is_published' => 'boolean',
            'title_i18n' => 'array',
            'excerpt_i18n' => 'array',
            'body_i18n' => 'array',
        ];
    }

    public function faq(): HasMany
    {
        return $this->hasMany(FaqItem::class)->where('is_published', true)->orderBy('sort')->orderBy('id');
    }

    /**
     * Блоки текста на языке посетителя.
     *
     * Свой текст языка — как есть; не вписан — разметка берётся из
     * русского текста, а переводится каждая строка отдельно: иначе
     * переводчик мог бы потерять пометки, и шаги рассыпались бы
     * в сплошные абзацы.
     *
     * @return list<array<string, mixed>>
     */
    public function blocks(?string $locale = null): array
    {
        $locale ??= app()->getLocale();
        $own = $this->own('body', $locale);

        if ($own !== '' || $locale === 'ru') {
            return PageBody::blocks($own);
        }

        $blocks = PageBody::blocks($this->body);
        app(ContentTranslation::class)->prefetch(PageBody::strings($blocks), $locale);

        return PageBody::map($blocks, fn (string $s): string => (string) ContentTranslation::text($s, $locale));
    }

    /**
     * Всё, что нужно вёрстке страницы.
     *
     * @return array{key: string, title: string, lead: string, blocks: list<array<string, mixed>>}
     */
    public function card(): array
    {
        return [
            'key' => $this->key,
            'title' => $this->localized('title'),
            'lead' => $this->localized('excerpt'),
            'blocks' => $this->blocks(),
        ];
    }

    /** Заголовок для поисковика: свой, иначе заголовок страницы. */
    public function seoTitle(): string
    {
        return $this->translatedMeta('meta_title') ?: $this->localized('title');
    }

    public function seoDescription(): string
    {
        return $this->translatedMeta('meta_description') ?: $this->localized('excerpt');
    }

    /** Поля для поисковика — только по-русски, другие языки переводятся. */
    private function translatedMeta(string $field): string
    {
        $value = trim((string) $this->getAttribute($field));

        return $value === '' ? '' : trim((string) ContentTranslation::text($value));
    }
}
