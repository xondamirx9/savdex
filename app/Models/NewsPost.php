<?php

declare(strict_types=1);

namespace App\Models;

use App\Jobs\TranslateNewsPost;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Support\Str;

/**
 * Новость площадки.
 *
 * Переехала из NewsRepository в базу: править новости не должно
 * означать выкатывать релиз.
 */
#[Fillable([
    'slug', 'category', 'title', 'excerpt', 'body', 'image_path',
    'read_time', 'is_published', 'published_at', 'sort', 'author_id',
])]
class NewsPost extends Model
{
    /** Рубрики. Их немного и они задают оформление обложки. */
    public const CATEGORIES = [
        'Обновления сервиса' => 'Обновления сервиса',
        'Тарифы и оплата' => 'Тарифы и оплата',
        'Аналитика рынка' => 'Аналитика рынка',
        'Полезное' => 'Полезное',
    ];

    /**
     * Ключи рубрик для словаря — в том же порядке, что CATEGORIES.
     *
     * @var list<string>
     */
    private const CATEGORY_KEYS = ['updates', 'pricing', 'market', 'useful'];

    protected function casts(): array
    {
        return [
            'is_published' => 'boolean',
            'published_at' => 'datetime',
            'title_i18n' => 'array',
            'excerpt_i18n' => 'array',
            'body_i18n' => 'array',
        ];
    }

    /**
     * Перевод — фоном после публикации.
     *
     * Повторной отправки нет: после первого прохода title_i18n уже
     * не null (пусть даже пустой), добор — по расписанию. Та же схема,
     * что у объявлений и тендеров.
     */
    protected static function booted(): void
    {
        static::saved(function (self $post): void {
            if ($post->is_published
                && $post->title_i18n === null
                && config('services.machine_translation.enabled')) {
                TranslateNewsPost::dispatch($post->id);
            }
        });
    }

    /**
     * Заголовок на языке посетителя.
     *
     * Оригинал пишется по-русски; машинный перевод появляется фоном
     * после публикации. Пока перевода нет — показывается оригинал:
     * русский заголовок лучше пустой карточки.
     */
    public function localizedTitle(?string $locale = null): string
    {
        return $this->localized($this->title_i18n, (string) $this->title, $locale);
    }

    public function localizedExcerpt(?string $locale = null): string
    {
        return $this->localized($this->excerpt_i18n, (string) $this->excerpt, $locale);
    }

    public function localizedBody(?string $locale = null): string
    {
        return $this->localized($this->body_i18n, (string) $this->body, $locale);
    }

    /** @param array<string, string>|null $translations */
    private function localized(?array $translations, string $original, ?string $locale): string
    {
        $locale ??= app()->getLocale();

        if ($locale === 'ru') {
            return $original;
        }

        return trim((string) ($translations[$locale] ?? '')) !== ''
            ? $translations[$locale]
            : $original;
    }

    public function author(): BelongsTo
    {
        return $this->belongsTo(User::class, 'author_id');
    }

    /** @param Builder<self> $query */
    public function scopePublished(Builder $query): void
    {
        $query->where('is_published', true)
            ->where(fn ($q) => $q->whereNull('published_at')->orWhere('published_at', '<=', now()));
    }

    /**
     * Абзацы текста.
     *
     * Хранится обычным текстом с пустыми строками между абзацами:
     * редактору не нужен HTML, а вывод всё равно идёт через <p>.
     */
    public function paragraphs(?string $locale = null): array
    {
        return collect(preg_split('/\R{2,}/u', $this->localizedBody($locale)))
            ->map(fn (string $p): string => trim($p))
            ->filter()
            ->values()
            ->all();
    }

    /** Время чтения: 180 слов в минуту — средняя скорость по-русски. */
    public function readTime(): string
    {
        if (filled($this->read_time)) {
            return $this->read_time;
        }

        $words = str_word_count(strip_tags((string) $this->body), 0, 'абвгдеёжзийклмнопрстуфхцчшщъыьэюяАБВГДЕЁЖЗИЙКЛМНОПРСТУФХЦЧШЩЪЫЬЭЮЯ');

        // Через словарь: «мин» посреди узбекской страницы читается
        // как недоделка, хотя цифра и верная
        return __('ui.news.read_time', ['count' => max(1, (int) ceil($words / 180))]);
    }

    /**
     * Рубрика на языке посетителя.
     *
     * Рубрик четыре, они выбираются из списка в админке — поэтому
     * перевод лежит в словаре, а не в базе. Незнакомое значение
     * показывается как есть: рубрику могли завести до словаря.
     */
    public static function categoryLabel(?string $category): string
    {
        $key = array_search((string) $category, array_keys(self::CATEGORIES), true);

        return $key === false
            ? (string) $category
            : __('ui.news.rubrics.'.self::CATEGORY_KEYS[$key]);
    }

    public static function makeSlug(string $title): string
    {
        return Str::slug(Str::transliterate($title)) ?: 'news';
    }
}
