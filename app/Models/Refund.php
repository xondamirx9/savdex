<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * Возврат по платежу.
 *
 * Возврат бывает частичным и не один: поле в платеже хранило бы только
 * последний и стирало бы предыдущие. Отдельная запись помнит все — с
 * причиной, автором и датой решения.
 */
#[Fillable([
    'payment_id', 'company_id', 'amount', 'currency', 'reason',
    'status', 'created_by', 'decided_by', 'decided_at', 'decision_note',
])]
class Refund extends Model
{
    use HasFactory;

    public const STATUS_REQUESTED = 'requested';

    public const STATUS_DONE = 'done';

    public const STATUS_REJECTED = 'rejected';

    /** @var array<string, string> */
    public const STATUSES = [
        self::STATUS_REQUESTED => 'Заявлен',
        self::STATUS_DONE => 'Проведён',
        self::STATUS_REJECTED => 'Отклонён',
    ];

    protected function casts(): array
    {
        return [
            'amount' => 'integer',
            'decided_at' => 'datetime',
        ];
    }

    public function payment(): BelongsTo
    {
        return $this->belongsTo(Payment::class);
    }

    public function company(): BelongsTo
    {
        return $this->belongsTo(Company::class);
    }

    public function author(): BelongsTo
    {
        return $this->belongsTo(User::class, 'created_by');
    }

    public function decidedBy(): BelongsTo
    {
        return $this->belongsTo(User::class, 'decided_by');
    }

    public function statusLabel(): string
    {
        return self::STATUSES[$this->status] ?? $this->status;
    }

    /** «429 500 сум» — с пробелами, иначе цифры не читаются. */
    public function money(): string
    {
        return number_format($this->amount, 0, ',', ' ').' '.$this->currency;
    }

    /** Решение принято — запись закрыта и больше не меняется по смыслу. */
    public function isDecided(): bool
    {
        return $this->status !== self::STATUS_REQUESTED;
    }
}
