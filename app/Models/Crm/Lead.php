<?php

declare(strict_types=1);

namespace App\Models\Crm;

use App\Models\Company;
use App\Models\User;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Database\Eloquent\Relations\MorphMany;
use Illuminate\Database\Eloquent\SoftDeletes;

/**
 * Лид — обращение, из которого может вырасти клиент.
 *
 * Лид без ответственного виден всем продавцам: новая заявка, закреплённая
 * ни за кем, иначе пролежит до первого распределения, а звонить по ней
 * надо сегодня.
 */
#[Fillable([
    'title', 'source', 'company_id', 'contact_id',
    'contact_name', 'contact_phone', 'contact_email',
    'owner_id', 'status', 'lost_reason', 'note',
])]
class Lead extends Model
{
    use HasFactory;
    use SoftDeletes;

    protected $table = 'crm_leads';

    public const STATUS_NEW = 'new';

    public const STATUS_WORKING = 'working';

    public const STATUS_QUALIFIED = 'qualified';

    public const STATUS_CONVERTED = 'converted';

    public const STATUS_LOST = 'lost';

    /** @var array<string, string> */
    public const STATUSES = [
        self::STATUS_NEW => 'Новый',
        self::STATUS_WORKING => 'В работе',
        self::STATUS_QUALIFIED => 'Квалифицирован',
        self::STATUS_CONVERTED => 'Стал сделкой',
        self::STATUS_LOST => 'Отказ',
    ];

    /** @var array<string, string> */
    public const SOURCES = [
        'site' => 'Форма на сайте',
        'call' => 'Звонок',
        'email' => 'Почта',
        'referral' => 'Рекомендация',
        'event' => 'Выставка',
        'outbound' => 'Холодный контакт',
        'other' => 'Другое',
    ];

    public function company(): BelongsTo
    {
        return $this->belongsTo(Company::class);
    }

    public function contact(): BelongsTo
    {
        return $this->belongsTo(Contact::class);
    }

    public function owner(): BelongsTo
    {
        return $this->belongsTo(User::class, 'owner_id');
    }

    public function tasks(): MorphMany
    {
        return $this->morphMany(Task::class, 'subject');
    }

    public function communications(): MorphMany
    {
        return $this->morphMany(Communication::class, 'subject');
    }

    /** Закрытые лиды не ждут действий и не должны маячить в работе. */
    public function scopeOpen(Builder $query): void
    {
        $query->whereNotIn('status', [self::STATUS_CONVERTED, self::STATUS_LOST]);
    }

    public function statusLabel(): string
    {
        return self::STATUSES[$this->status] ?? $this->status;
    }

    /**
     * Кому звонить: из карточки контакта, иначе из самой заявки.
     *
     * Имя метода не совпадает ни с одной колонкой: Eloquent принимает
     * обращение к несуществующему атрибуту за связь и требует, чтобы
     * одноимённый метод вернул отношение.
     */
    public function contactName(): ?string
    {
        return $this->contact?->name ?? $this->contact_name;
    }
}
