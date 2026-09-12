<?php

declare(strict_types=1);

namespace App\Models;

use App\Support\SearchText;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\HasMany;
use Illuminate\Support\Str;

/**
 * IT-задача — заказ на разработку или IT-услугу от компании площадки.
 *
 * Публикуется из кабинета сразу, без модерации: заказчик — проверенная
 * компания, а задача не товар. IT-исполнители (компании с флагом
 * is_it_provider) откликаются, разговор идёт в чате кабинета, отклик
 * списывает квоту тарифа так же, как отклик на объявление.
 */
#[Fillable([
    'company_id', 'user_id', 'slug', 'title', 'description', 'service_type', 'stack',
    'budget_type', 'budget_from', 'budget_to', 'currency', 'deadline_at',
    'status', 'published_at', 'closed_at',
])]
class ItTask extends Model
{
    use HasFactory;

    public const STATUS_ACTIVE = 'active';

    public const STATUS_CLOSED = 'closed';

    public const STATUS_ARCHIVED = 'archived';

    public const STATUSES = [
        self::STATUS_ACTIVE => 'Открыта',
        self::STATUS_CLOSED => 'Закрыта',
        self::STATUS_ARCHIVED => 'В архиве',
    ];

    /** Виды IT-услуг: код → подпись. Те же коды — специализации исполнителей. */
    public const SERVICE_TYPES = [
        'web' => 'Сайты и веб-приложения',
        'mobile' => 'Мобильные приложения',
        'erp' => '1С, учёт и ERP',
        'integration' => 'Интеграции и API',
        'design' => 'Дизайн и UX',
        'automation' => 'Автоматизация и боты',
        'support' => 'Поддержка и администрирование',
        'other' => 'Другое',
    ];

    public const BUDGET_TYPES = ['fixed', 'range', 'negotiable'];

    public const CURRENCIES = ['UZS', 'USD'];

    public const MAX_STACK = 10;

    protected function casts(): array
    {
        return [
            'stack' => 'array',
            'budget_from' => 'decimal:2',
            'budget_to' => 'decimal:2',
            'deadline_at' => 'date',
            'published_at' => 'datetime',
            'closed_at' => 'datetime',
            'responses_count' => 'integer',
            'views_count' => 'integer',
        ];
    }

    protected static function booted(): void
    {
        static::saving(function (self $task): void {
            $task->search_text = SearchText::index(implode(' ', array_filter([
                $task->title,
                (string) $task->description,
                implode(' ', $task->stack ?? []),
            ])));
        });

        static::created(function (self $task): void {
            if (blank($task->slug)) {
                $task->slug = self::makeSlug($task->title, $task->id);
                $task->saveQuietly();
            }
        });
    }

    public function company(): BelongsTo
    {
        return $this->belongsTo(Company::class);
    }

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }

    public function files(): HasMany
    {
        return $this->hasMany(ItTaskFile::class)->orderBy('id');
    }

    public function threads(): HasMany
    {
        return $this->hasMany(MessageThread::class);
    }

    /** @param Builder<self> $query */
    public function scopeActive(Builder $query): void
    {
        $query->where('status', self::STATUS_ACTIVE);
    }

    /** @param Builder<self> $query */
    public function scopeSearch(Builder $query, string $term): void
    {
        $query->where('search_text', 'like', '%'.SearchText::normalize($term).'%');
    }

    public function isActive(): bool
    {
        return $this->status === self::STATUS_ACTIVE;
    }

    public function serviceTypeLabel(): string
    {
        return self::SERVICE_TYPES[$this->service_type] ?? $this->service_type;
    }

    public static function makeSlug(string $title, int $id): string
    {
        $base = Str::slug(Str::transliterate($title));

        return Str::limit($base ?: 'task', 60, '').'-'.$id;
    }
}
