<?php

declare(strict_types=1);

namespace App\Models;

use App\Jobs\TranslateListing;
use App\Support\SearchText;
use Database\Factories\ListingFactory;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\SoftDeletes;
use Illuminate\Support\Str;

/**
 * Объявление — предложение товара или запрос на закупку.
 */
#[Fillable([
    'company_id', 'user_id', 'category_id', 'city_id', 'type', 'slug', 'title',
    'description', 'price', 'bundle_price', 'currency', 'unit', 'price_negotiable', 'min_order',
    'delivery_terms', 'payment_terms', 'status', 'wizard_step', 'published_at', 'expires_at', 'tags',
    // Заметка модерации правится из админки; без неё форма молча
    // теряла бы текст, который видит владелец объявления
    'moderation_note',
])]
class Listing extends Model
{
    /** @use HasFactory<ListingFactory> */
    use HasFactory;

    use SoftDeletes;

    public const STATUS_DRAFT = 'draft';

    public const STATUS_MODERATION = 'moderation';

    public const STATUS_ACTIVE = 'active';

    public const STATUS_REJECTED = 'rejected';

    public const STATUS_EXPIRED = 'expired';

    public const STATUS_ARCHIVED = 'archived';

    public const TYPE_SUPPLY = 'supply';

    public const TYPE_DEMAND = 'demand';

    /** Срок жизни публикации по умолчанию. */
    public const LIFETIME_DAYS = 90;

    /**
     * @return array<string, string>
     */
    protected function casts(): array
    {
        return [
            'price' => 'decimal:2',
            'bundle_price' => 'decimal:2',
            'price_negotiable' => 'boolean',
            'published_at' => 'datetime',
            'expires_at' => 'datetime',
            'tags' => 'array',
            'title_i18n' => 'array',
            'description_i18n' => 'array',
        ];
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
        $locale ??= app()->getLocale();

        if ($locale === 'ru') {
            return $this->title;
        }

        return trim((string) ($this->title_i18n[$locale] ?? '')) !== ''
            ? $this->title_i18n[$locale]
            : $this->title;
    }

    /** Описание на языке посетителя — по тем же правилам. */
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

    public function company(): BelongsTo
    {
        return $this->belongsTo(Company::class);
    }

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }

    public function category(): BelongsTo
    {
        return $this->belongsTo(Category::class);
    }

    public function city(): BelongsTo
    {
        return $this->belongsTo(City::class);
    }

    public function images(): HasMany
    {
        return $this->hasMany(ListingImage::class)->orderBy('sort');
    }

    public function attributes(): HasMany
    {
        return $this->hasMany(ListingAttribute::class);
    }

    public function stats(): HasMany
    {
        return $this->hasMany(ListingStat::class);
    }

    public function promotions(): HasMany
    {
        return $this->hasMany(Promotion::class);
    }

    public function activePromotions(): HasMany
    {
        return $this->promotions()->where('status', 'active');
    }

    protected static function booted(): void
    {
        /*
         * Нормализованный текст пересобирается при каждом сохранении.
         *
         * Приведение регистра делается здесь, а не в SQL: lower() в SQLite
         * не трогает кириллицу, а LIKE в PostgreSQL регистрозависим —
         * поиск вёл бы себя по-разному в тестах и в бою.
         */
        static::saving(function (self $listing): void {
            // Обе графики разом: узбекская аудитория ищет латиницей
            // («sement»), а объявления пишутся кириллицей — и наоборот.
            // Переводы заголовка тоже в индексе: «cement blocks»
            // должно находить русское объявление
            $listing->search_text = SearchText::index(implode(' ', array_filter([
                $listing->title,
                (string) $listing->description,
                ...array_values($listing->title_i18n ?? []),
            ])));
        });

        /*
         * Перевод — фоном после публикации: четыре обращения
         * к внешнему сервису не должны задерживать сохранение.
         * Повторной отправки нет: после первого прохода title_i18n
         * уже не null (пусть даже пустой), добор — по расписанию.
         */
        static::saved(function (self $listing): void {
            if ($listing->status === self::STATUS_ACTIVE
                && $listing->title_i18n === null
                && config('services.machine_translation.enabled')) {
                TranslateListing::dispatch($listing->id);
            }
        });
    }

    /** @param Builder<self> $query */
    public function scopeActive(Builder $query): void
    {
        $query->where('status', self::STATUS_ACTIVE);
    }

    /**
     * Поиск по объявлениям.
     *
     * @param  Builder<self>  $query
     */
    public function scopeSearch(Builder $query, string $term): void
    {
        $needle = '%'.SearchText::normalize($term).'%';

        $query->where('search_text', 'like', $needle);
    }

    /** @param Builder<self> $query */
    public function scopeOfStatus(Builder $query, string $status): void
    {
        $query->where('status', $status);
    }

    public function isExpiringSoon(int $days = 7): bool
    {
        return $this->status === self::STATUS_ACTIVE
            && $this->expires_at !== null
            && $this->expires_at->isBefore(now()->addDays($days));
    }

    /** Конверсия из просмотра карточки в раскрытие контакта. */
    public function conversion(): float
    {
        return $this->views_count > 0
            ? round($this->unlocks_count / $this->views_count * 100, 1)
            : 0.0;
    }

    /**
     * Адрес объявления. Из заголовка берётся хвост: он информативнее
     * порядкового номера и переживает смену названия — id в конце
     * гарантирует уникальность без запроса к базе.
     */
    public static function makeSlug(string $title, int $id): string
    {
        $base = Str::slug(Str::transliterate($title));

        return Str::limit($base, 60, '').'-'.$id;
    }
}
