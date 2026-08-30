<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\BelongsToMany;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Database\Eloquent\Relations\HasOne;
use Illuminate\Database\Eloquent\SoftDeletes;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Str;

/**
 * Компания — владелец объявлений, кошелька и подписки.
 *
 * @property int $id
 * @property string $name
 * @property int $verification_level
 * @property float $rating
 */
#[Fillable([
    'slug', 'name', 'legal_name', 'tin',
    'country_id', 'city_id', 'address', 'lat', 'lng',
    'type', 'primary_role', 'custom_category', 'description', 'logo_path', 'cover_path', 'website',
    'phone', 'email', 'telegram', 'whatsapp', 'contact_person',
    'founded_year', 'employees_range', 'turnover_range',
    'verification_level', 'verified_at', 'verified_by',
    'rating', 'reviews_count', 'completed_deals_count', 'response_time_hours',
    'status', 'blocked_reason', 'blocked_at',
])]
class Company extends Model
{
    use HasFactory;
    use SoftDeletes;

    /** Уровни верификации (§5.3 ТЗ). Выдаёт только модерация. */
    public const VERIFICATION_NONE = 0;

    public const VERIFICATION_CONTACTS = 1;

    public const VERIFICATION_COMPANY = 2;

    public const VERIFICATION_EXTENDED = 3;

    public const STATUS_ACTIVE = 'active';

    /**
     * Типы компаний берутся из справочника company_types — он правится
     * из админки. Константа осталась запасным вариантом на случай,
     * когда справочник ещё не наполнен: пустой список в форме
     * регистрации не даст завести компанию вообще.
     *
     * @return array<string, string>
     */
    public static function typeOptions(): array
    {
        $fromDirectory = CompanyType::options();

        return $fromDirectory !== [] ? $fromDirectory : self::FALLBACK_TYPES;
    }

    public const FALLBACK_TYPES = [
        'manufacturer' => 'Производитель',
        'importer' => 'Импортёр',
        'distributor' => 'Дистрибьютор',
        'trader' => 'Торговая компания',
        'service' => 'Услуги',
    ];

    /** Человеческое название типа этой компании. */
    public function typeLabel(): ?string
    {
        return $this->type !== null
            ? (self::typeOptions()[$this->type] ?? $this->type)
            : null;
    }

    public const STATUS_PENDING = 'pending';

    public const STATUS_BLOCKED = 'blocked';

    protected function casts(): array
    {
        return [
            'verified_at' => 'datetime',
            'blocked_at' => 'datetime',
            'lat' => 'decimal:7',
            'lng' => 'decimal:7',
            'rating' => 'decimal:2',
            'verification_level' => 'integer',
            'founded_year' => 'integer',
            'reviews_count' => 'integer',
            'completed_deals_count' => 'integer',
        ];
    }

    protected static function booted(): void
    {
        static::creating(function (self $company): void {
            $company->slug ??= static::makeSlug($company->name);
        });
    }

    /**
     * Slug из названия. Кириллица и узбекская латиница транслитерируются,
     * поэтому Str::slug() недостаточно — он вырезает кириллицу целиком.
     */
    public static function makeSlug(string $name): string
    {
        $base = Str::slug(Str::transliterate($name)) ?: 'company';
        $slug = $base;
        $i = 2;

        while (static::withTrashed()->where('slug', $slug)->exists()) {
            $slug = $base.'-'.$i++;
        }

        return $slug;
    }

    // ── Связи ────────────────────────────────────────────────

    public function users(): HasMany
    {
        return $this->hasMany(User::class);
    }

    public function owner(): HasMany
    {
        return $this->hasMany(User::class)->where('company_role', 'owner');
    }

    public function country(): BelongsTo
    {
        return $this->belongsTo(Country::class);
    }

    public function city(): BelongsTo
    {
        return $this->belongsTo(City::class);
    }

    public function attributes(): HasMany
    {
        return $this->hasMany(CompanyAttribute::class);
    }

    public function documents(): HasMany
    {
        return $this->hasMany(CompanyDocument::class);
    }

    /** Все контакты компании: телефоны, почты, мессенджеры, сайт. */
    public function contacts(): HasMany
    {
        return $this->hasMany(CompanyContact::class)->ordered();
    }

    /** Публичные контакты — те, что компания разрешила показывать. */
    public function publicContacts(): HasMany
    {
        return $this->contacts()->visible();
    }

    /** Категории деятельности — по ним компанию находят в каталоге. */
    public function categories(): BelongsToMany
    {
        return $this->belongsToMany(Category::class, 'company_category');
    }

    public function listings(): HasMany
    {
        return $this->hasMany(Listing::class);
    }

    public function activeListings(): HasMany
    {
        return $this->listings()->where('status', Listing::STATUS_ACTIVE);
    }

    public function wallet(): HasOne
    {
        return $this->hasOne(Wallet::class);
    }

    /**
     * Действующая подписка компании.
     *
     * Проверяется и срок, а не только статус: в expired подписку
     * переводит плановая команда, и пока она не отработала — а на
     * хостинге планировщик может быть не заведён вовсе — истёкшая
     * подписка продолжала давать доступ. Для подарочного месяца
     * по промокоду это означало бесплатный платный тариф навсегда.
     */
    public function subscription(): HasOne
    {
        return $this->hasOne(Subscription::class)
            ->where('status', 'active')
            ->where(fn ($q) => $q->whereNull('ends_at')->orWhere('ends_at', '>', now()))
            ->latestOfMany();
    }

    /** Контакты, которые открыла эта компания. */
    public function unlocks(): HasMany
    {
        return $this->hasMany(ContactUnlock::class);
    }

    /** Кто открыл контакты этой компании. */
    public function unlockedBy(): HasMany
    {
        return $this->hasMany(ContactUnlock::class, 'target_company_id');
    }

    public function reviews(): HasMany
    {
        return $this->hasMany(Review::class)->where('status', 'published');
    }

    public function promotions(): HasMany
    {
        return $this->hasMany(Promotion::class);
    }

    public function payments(): HasMany
    {
        return $this->hasMany(Payment::class);
    }

    public function paymentMethods(): HasMany
    {
        return $this->hasMany(PaymentMethod::class);
    }

    public function events(): HasMany
    {
        return $this->hasMany(ActivityEvent::class)->latest();
    }

    public function searchHits(): HasMany
    {
        return $this->hasMany(SearchHit::class);
    }

    /**
     * Тариф компании. Free — когда подписки нет: тариф есть всегда,
     * иначе каждый расчёт лимитов приходится оборачивать в проверку null.
     *
     * Если справочник тарифов не наполнен, возвращается несохранённый
     * Free с ограничениями по умолчанию. Раньше здесь стоял firstOrFail,
     * и на установке без PlanSeeder весь кабинет и визитки отвечали 500 —
     * отсутствие строки в справочнике не должно ронять витрину.
     */
    public function plan(): Plan
    {
        return $this->subscription?->plan
            ?? Plan::query()->where('code', Plan::FREE)->first()
            ?? new Plan([
                'code' => Plan::FREE,
                'name' => 'Free',
                'price_usd' => 0,
                'period_days' => 30,
                'listing_days' => 30,
                'listings_limit' => 4,
                'contacts_limit' => 3,
                'promo_units' => 0,
                'verification_days' => 5,
            ]);
    }

    // ── Визитка ──────────────────────────────────────────────

    /**
     * Публичный адрес карточки компании.
     * Используется в QR-коде и при отправке визитки (§5.2 FR-COMP-05).
     */
    public function publicUrl(): string
    {
        return url('/company/'.$this->slug);
    }

    /**
     * Данные визитки — то, что видно в шапке страницы компании
     * до раскрытия контактов: кто это, где находится, чем занимается.
     *
     * @return array<string, mixed>
     */
    public function businessCard(): array
    {
        return [
            'name' => $this->name,
            'legal_name' => $this->legal_name,
            'tin' => $this->tin,
            'type' => $this->type,
            'type_label' => $this->typeLabel(),
            'custom_category' => $this->custom_category,
            'country' => $this->country?->name(),
            'city' => $this->city?->name(),
            'address' => $this->address,
            'coords' => $this->lat && $this->lng ? ['lat' => (float) $this->lat, 'lng' => (float) $this->lng] : null,
            'description' => $this->description,
            'founded_year' => $this->founded_year,
            'employees_range' => $this->employees_range,
            'verification_level' => $this->verification_level,
            'rating' => (float) $this->rating,
            'reviews_count' => $this->reviews_count,
            'logo' => $this->logoUrl(),
            'cover' => $this->coverUrl(),
            'slug' => $this->slug,
            'url' => $this->publicUrl(),
        ];
    }

    // ── Поведение ────────────────────────────────────────────

    /**
     * Адрес логотипа; null — компания его не загружала.
     *
     * Проверяется и наличие файла: загрузки времён эфемерного хранилища
     * пропали с диска, и битая картинка в шапке хуже, чем инициалы.
     */
    public function logoUrl(): ?string
    {
        if ($this->logo_path === null || ! Storage::disk('public')->exists($this->logo_path)) {
            return null;
        }

        return asset('storage/'.$this->logo_path);
    }

    /** Адрес обложки визитки; null — остаётся фирменный градиент. */
    public function coverUrl(): ?string
    {
        if ($this->cover_path === null || ! Storage::disk('public')->exists($this->cover_path)) {
            return null;
        }

        return asset('storage/'.$this->cover_path);
    }

    /**
     * Инициалы для плашки-логотипа: «ООО «Стройбаза»» → «СБ».
     * Используются, пока компания не загрузила своё изображение.
     */
    public function initials(): string
    {
        $words = preg_split('/[\s«»"\']+/u', (string) $this->name, -1, PREG_SPLIT_NO_EMPTY) ?: [];

        // Организационно-правовая форма ничего не говорит о компании,
        // а «ОО» вместо «СБ» на плашке выглядит одинаково у половины базы
        $skip = ['ООО', 'ЧП', 'АО', 'ЗАО', 'ИП', 'МЧЖ', 'ЖЧЖ', 'LLC', 'JSC'];
        $words = array_values(array_filter(
            $words,
            fn (string $w): bool => ! in_array(mb_strtoupper($w), $skip, true),
        ));

        if ($words === []) {
            return '?';
        }

        // Из одного слова берём две первые буквы: одна буква на плашке
        // выглядит незаконченной и хуже различает компании
        if (count($words) === 1) {
            return mb_strtoupper(mb_substr($words[0], 0, 2));
        }

        return implode('', array_map(
            fn (string $w): string => mb_strtoupper(mb_substr($w, 0, 1)),
            array_slice($words, 0, 2),
        ));
    }

    public function isVerified(): bool
    {
        return $this->verification_level >= self::VERIFICATION_COMPANY;
    }

    public function isBlocked(): bool
    {
        return $this->status === self::STATUS_BLOCKED;
    }

    /**
     * Заполненность профиля в процентах.
     * Показывается прогресс-баром (§5.2 FR-COMP-01) — заполненный профиль
     * получает заметно больше обращений, поэтому мотивируем дозаполнить.
     */
    public function profileCompleteness(): int
    {
        $checks = [
            'name' => filled($this->name),
            'type' => filled($this->type),
            'city' => filled($this->city_id),
            'phone' => filled($this->phone),
            'email' => filled($this->email),
            'tin' => filled($this->tin),
            'address' => filled($this->address),
            'description' => mb_strlen((string) $this->description) >= 100,
            'logo' => filled($this->logo_path),
            'documents' => $this->hasApprovedDocuments(),
        ];

        $done = count(array_filter($checks));

        return (int) round($done / count($checks) * 100);
    }

    /**
     * Есть ли одобренные документы. Списки подгружают ответ подзапросом
     * (withExists в ListingCard::relations) — тогда запроса здесь нет.
     */
    public function hasApprovedDocuments(): bool
    {
        if (array_key_exists('has_approved_documents', $this->attributes)) {
            return (bool) $this->attributes['has_approved_documents'];
        }

        return $this->documents()->where('moderation_status', 'approved')->exists();
    }

    /** Чего не хватает в профиле — для подсказок в кабинете. */
    public function missingProfileFields(): array
    {
        $labels = [
            'tin' => __('company.field.tin'),
            'address' => __('company.field.address'),
            'description' => __('company.field.description'),
            'logo' => __('company.field.logo'),
            'documents' => __('company.field.documents'),
        ];

        $missing = [];

        if (blank($this->tin)) {
            $missing[] = $labels['tin'];
        }
        if (blank($this->address)) {
            $missing[] = $labels['address'];
        }
        if (mb_strlen((string) $this->description) < 100) {
            $missing[] = $labels['description'];
        }
        if (blank($this->logo_path)) {
            $missing[] = $labels['logo'];
        }
        if (! $this->documents()->where('moderation_status', 'approved')->exists()) {
            $missing[] = $labels['documents'];
        }

        return $missing;
    }
}
