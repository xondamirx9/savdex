<?php

declare(strict_types=1);

namespace App\Models;

use App\Jobs\TranslateTender;
use App\Support\SearchText;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Support\Str;

/**
 * Тендер — объявление о закупке, размещённое площадкой.
 *
 * Заводится менеджером из админки (по одному или загрузкой файла)
 * и показывается на витрине отдельным разделом «Тендеры». В отличие
 * от объявлений компаний, у тендера нет автора-компании и модерации:
 * опубликовал менеджер — значит, проверил.
 */
#[Fillable([
    'slug', 'title', 'description', 'customer', 'category_id', 'country_id', 'location',
    'budget', 'currency', 'deadline_at', 'source_url',
    'contact_name', 'contact_phone', 'contact_email',
    'status', 'published_at', 'author_id',
])]
class Tender extends Model
{
    use HasFactory;

    public const STATUS_DRAFT = 'draft';

    public const STATUS_PUBLISHED = 'published';

    public const STATUS_ARCHIVED = 'archived';

    public const STATUSES = [
        self::STATUS_DRAFT => 'Черновик',
        self::STATUS_PUBLISHED => 'Опубликован',
        self::STATUS_ARCHIVED => 'В архиве',
    ];

    public const CURRENCIES = ['UZS', 'USD', 'EUR', 'RUB', 'CNY', 'KZT'];

    protected function casts(): array
    {
        return [
            'budget' => 'decimal:2',
            'deadline_at' => 'datetime',
            'published_at' => 'datetime',
            'title_i18n' => 'array',
            'description_i18n' => 'array',
            'views_count' => 'integer',
        ];
    }

    protected static function booted(): void
    {
        static::saving(function (self $tender): void {
            $tender->search_text = SearchText::index(implode(' ', array_filter([
                $tender->title,
                (string) $tender->description,
                (string) $tender->customer,
                ...array_values($tender->title_i18n ?? []),
            ])));
        });

        // Адрес строится из заголовка и id, а id есть только после вставки
        static::created(function (self $tender): void {
            if (blank($tender->slug)) {
                $tender->slug = self::makeSlug($tender->title, $tender->id);
                $tender->saveQuietly();
            }
        });

        static::saved(function (self $tender): void {
            if ($tender->status === self::STATUS_PUBLISHED
                && $tender->title_i18n === null
                && config('services.machine_translation.enabled')) {
                TranslateTender::dispatch($tender->id);
            }
        });
    }

    public function category(): BelongsTo
    {
        return $this->belongsTo(Category::class);
    }

    public function country(): BelongsTo
    {
        return $this->belongsTo(Country::class);
    }

    public function author(): BelongsTo
    {
        return $this->belongsTo(User::class, 'author_id');
    }

    /** @param Builder<self> $query */
    public function scopePublished(Builder $query): void
    {
        $query->where('status', self::STATUS_PUBLISHED)
            ->where(fn (Builder $q) => $q->whereNull('published_at')->orWhere('published_at', '<=', now()));
    }

    /** Приём заявок ещё идёт: срок не задан или не прошёл. */
    public function scopeOpen(Builder $query): void
    {
        $query->where(fn (Builder $q) => $q->whereNull('deadline_at')->orWhere('deadline_at', '>=', now()));
    }

    /** @param Builder<self> $query */
    public function scopeSearch(Builder $query, string $term): void
    {
        $query->where('search_text', 'like', '%'.SearchText::normalize($term).'%');
    }

    public function isClosed(): bool
    {
        return $this->deadline_at !== null && $this->deadline_at->isPast();
    }

    public function localizedTitle(?string $locale = null): string
    {
        $locale ??= app()->getLocale();

        if ($locale === 'ru') {
            return $this->title;
        }

        return trim((string) ($this->title_i18n[$locale] ?? '')) !== ''
            ? $this->title_i18n[$locale]
            : $this->title;
    }

    public function localizedDescription(?string $locale = null): ?string
    {
        $locale ??= app()->getLocale();

        if ($locale === 'ru') {
            return $this->description;
        }

        return trim((string) ($this->description_i18n[$locale] ?? '')) !== ''
            ? $this->description_i18n[$locale]
            : $this->description;
    }

    public static function makeSlug(string $title, int $id): string
    {
        $base = Str::slug(Str::transliterate($title));

        return Str::limit($base ?: 'tender', 60, '').'-'.$id;
    }
}
