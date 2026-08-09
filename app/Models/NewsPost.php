<?php

declare(strict_types=1);

namespace App\Models;

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

    protected function casts(): array
    {
        return ['is_published' => 'boolean', 'published_at' => 'datetime'];
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
    public function paragraphs(): array
    {
        return collect(preg_split('/\R{2,}/u', (string) $this->body))
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

        return max(1, (int) ceil($words / 180)).' мин';
    }

    public static function makeSlug(string $title): string
    {
        return Str::slug(Str::transliterate($title)) ?: 'news';
    }
}
