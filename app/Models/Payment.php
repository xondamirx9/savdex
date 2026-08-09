<?php

declare(strict_types=1);

namespace App\Models;

use App\Services\OrderService;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;
use Illuminate\Support\Carbon;

/** Платёж: подписка, пакет кредитов или единицы продвижения. */
#[Fillable([
    'company_id', 'payment_method_id', 'subscription_id', 'plan_id', 'credit_pack_id',
    'number', 'purpose', 'description',
    'amount', 'currency', 'provider', 'external_id', 'status', 'paid_at', 'invoice_path',
    'confirmed_by', 'admin_note',
])]
class Payment extends Model
{
    /** Подписи статусов — те же, что видит покупатель в кабинете. */
    public const STATUSES = [
        'pending' => 'Ожидает оплаты',
        'paid' => 'Оплачен',
        'failed' => 'Отменён',
        'refunded' => 'Возвращён',
    ];

    protected function casts(): array
    {
        return ['paid_at' => 'datetime', 'amount' => 'integer'];
    }

    public function company(): BelongsTo
    {
        return $this->belongsTo(Company::class);
    }

    public function method(): BelongsTo
    {
        return $this->belongsTo(PaymentMethod::class, 'payment_method_id');
    }

    public function plan(): BelongsTo
    {
        return $this->belongsTo(Plan::class);
    }

    public function creditPack(): BelongsTo
    {
        return $this->belongsTo(CreditPack::class);
    }

    /** Кто подтвердил поступление денег. */
    public function confirmedBy(): BelongsTo
    {
        return $this->belongsTo(User::class, 'confirmed_by');
    }

    public function isPending(): bool
    {
        return $this->status === 'pending';
    }

    public function statusLabel(): string
    {
        return self::STATUSES[$this->status] ?? $this->status;
    }

    /** Сумма для человека: «1 152 000 сум». */
    public function amountLabel(): string
    {
        return number_format($this->amount, 0, ',', ' ').' '.($this->currency === 'UZS' ? 'сум' : $this->currency);
    }

    /**
     * До какого числа ждём оплату.
     *
     * Считается от даты счёта, а не хранится: срок один для всех
     * и меняется правкой константы, а не обновлением таблицы.
     */
    public function expiresAt(): ?Carbon
    {
        return $this->isPending()
            ? $this->created_at?->copy()->addDays(OrderService::EXPIRES_DAYS)
            : null;
    }
}
