<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/** Подписка компании на тариф. */
#[Fillable([
    'company_id', 'plan_id', 'status', 'started_at', 'ends_at', 'auto_renew', 'cancelled_at',
    'source', 'granted_by', 'grant_reason',
])]
class Subscription extends Model
{
    /** Оплачена через кассу. */
    public const SOURCE_PAYMENT = 'payment';

    /** Выдана администратором вручную: VIP, дебиторка, компенсация. */
    public const SOURCE_MANUAL = 'manual';

    /**
     * Активирована промокодом — бесплатный период тарифа.
     *
     * Отдельно от manual: подарок администратора и акция для новых
     * компаний считаются по-разному, а в отчёте о выручке обе не должны
     * выглядеть оплатой.
     */
    public const SOURCE_PROMO = 'promo';

    protected function casts(): array
    {
        return [
            'started_at' => 'datetime',
            'ends_at' => 'datetime',
            'cancelled_at' => 'datetime',
            'auto_renew' => 'boolean',
        ];
    }

    public function company(): BelongsTo
    {
        return $this->belongsTo(Company::class);
    }

    public function plan(): BelongsTo
    {
        return $this->belongsTo(Plan::class);
    }

    /** Кто выдал подписку вручную. */
    public function grantedBy(): BelongsTo
    {
        return $this->belongsTo(User::class, 'granted_by');
    }

    public function isManual(): bool
    {
        return $this->source === self::SOURCE_MANUAL;
    }

    public function isActive(): bool
    {
        return $this->status === 'active'
            && ($this->ends_at === null || $this->ends_at->isFuture());
    }

    /** Сколько дней осталось; null — бессрочная. */
    public function daysLeft(): ?int
    {
        if ($this->ends_at === null) {
            return null;
        }

        // Отрицательное значение округляем до нуля: «осталось −4 дня»
        // ничего не сообщает, а просроченную подписку видно по статусу
        return max(0, (int) now()->startOfDay()->diffInDays($this->ends_at->startOfDay(), false));
    }
}
