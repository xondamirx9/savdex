<?php

declare(strict_types=1);

namespace App\Models;

use App\Jobs\TranslateListing;
use App\Services\MachineTranslator;
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
    'company_id', 'user_id', 'source', 'category_id', 'city_id', 'type', 'slug', 'title',
    'description', 'price', 'bundle_price', 'currency', 'unit', 'price_negotiable', 'min_order',
    'delivery_terms', 'payment_terms', 'status', 'wizard_step', 'published_at', 'expires_at', 'tags',
    // Заметка модерации правится из админки; без неё форма молча
    // теряла бы текст, который видит владелец объявления
    'moderation_note',
    // Переводы правятся в админке по языкам; кабинет их не присылает
    'title_i18n', 'description_i18n', 'delivery_terms_i18n', 'payment_terms_i18n',
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

    /** Написано продавцом в кабинете. */
    public const SOURCE_CABINET = 'cabinet';

    /** Загружено администратором из книги Excel. */
    public const SOURCE_IMPORT = 'import';

    /**
     * Поля, у которых есть версия на каждом языке.
     *
     * Русский оригинал лежит в самой колонке, переводы — в колонке
     * с суффиксом _i18n: {en: ..., uz: ..., tr: ..., zh: ...}.
     *
     * @var list<string>
     */
    public const TRANSLATABLE = ['title', 'description', 'delivery_terms', 'payment_terms'];

    /**
     * Предел длины текстов — один на кабинет, админку и загрузку.
     *
     * Загрузка обязана проверять то же, что форма: иначе книга кладёт
     * заголовок в 120 знаков, а форма админки потом не даёт сохранить
     * объявление, пока перевод не укоротят.
     *
     * @var array<string, int>
     */
    public const MAX_LENGTH = [
        'title' => 90,
        'description' => 5000,
        'delivery_terms' => 2000,
        'payment_terms' => 2000,
    ];

    /** Срок жизни публикации по умолчанию. */
    public const LIFETIME_DAYS = 90;

    /** Больше десяти фотографий никто не листает, а место они занимают. */
    public const MAX_IMAGES = 10;

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
            'delivery_terms_i18n' => 'array',
            'payment_terms_i18n' => 'array',
        ];
    }

    /**
     * Заголовок на языке посетителя.
     *
     * Оригинал пишется по-русски; перевод либо загружен из книги
     * Excel, либо сделан машиной фоном после публикации. Пока
     * перевода нет — показывается оригинал: русский заголовок лучше
     * пустой карточки.
     */
    public function localizedTitle(?string $locale = null): string
    {
        return (string) $this->localized('title', $locale);
    }

    /** Описание на языке посетителя — по тем же правилам. */
    public function localizedDescription(?string $locale = null): ?string
    {
        return $this->localized('description', $locale);
    }

    public function localizedDeliveryTerms(?string $locale = null): ?string
    {
        return $this->localized('delivery_terms', $locale);
    }

    public function localizedPaymentTerms(?string $locale = null): ?string
    {
        return $this->localized('payment_terms', $locale);
    }

    /** Перевод поля есть и не пустой. */
    public function hasTranslation(string $field, string $locale): bool
    {
        if ($locale === 'ru') {
            return trim((string) $this->{$field}) !== '';
        }

        return trim((string) ($this->{$field.'_i18n'}[$locale] ?? '')) !== '';
    }

    private function localized(string $field, ?string $locale): ?string
    {
        $locale ??= app()->getLocale();

        return $this->hasTranslation($field, $locale) && $locale !== 'ru'
            ? $this->{$field.'_i18n'}[$locale]
            : $this->{$field};
    }

    public function isImported(): bool
    {
        return $this->source === self::SOURCE_IMPORT;
    }

    /**
     * Есть язык каталога, на который заголовок ещё не переведён.
     *
     * Раньше переводы были либо все, либо никакие, и хватало проверки
     * на null. Загрузка из книги и вкладки в админке дают частичные
     * наборы — английский есть, узбекского нет, — и машинному
     * переводчику нужно понимать, что добирать есть что.
     */
    public function missingTranslations(): bool
    {
        $present = array_keys(array_filter(
            $this->title_i18n ?? [],
            fn (mixed $text): bool => trim((string) $text) !== '',
        ));

        return array_diff(MachineTranslator::TARGETS, $present) !== [];
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
         *
         * Только в момент публикации, а не при каждом сохранении:
         * задача сама сохраняет объявление, и при сбое части языков
         * недостающие остались бы — сохранение запускало бы задачу
         * снова, и так по кругу. Что не сложилось — доберёт
         * расписание (routes/console.php).
         */
        static::saved(function (self $listing): void {
            if ($listing->status === self::STATUS_ACTIVE
                && ($listing->wasRecentlyCreated || $listing->wasChanged('status'))
                && $listing->missingTranslations()
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
     * Объявления, у которых нет заголовка хотя бы на одном языке
     * каталога: null, пустой набор и частичный подходят одинаково.
     *
     * @param  Builder<self>  $query
     */
    public function scopeLackingTranslations(Builder $query): void
    {
        $query->where(function (Builder $q): void {
            foreach (MachineTranslator::TARGETS as $locale) {
                $q->orWhereJsonDoesntContainKey('title_i18n->'.$locale);
            }
        });
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
