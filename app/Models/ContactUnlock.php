<?php

declare(strict_types=1);

namespace App\Models;

use Database\Factories\ContactUnlockFactory;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * Раскрытый контакт компании.
 *
 * Одна строка обслуживает два раздела кабинета: «Мои контакты» для того,
 * кто открыл, и «Кто мной интересуется» для того, чьи контакты открыли.
 */
#[Fillable([
    'company_id', 'target_company_id', 'user_id', 'listing_id', 'credits_spent',
    'status', 'note', 'complaint_status', 'complaint_reason', 'complained_at', 'refunded',
    // След решения модератора: кто, когда и с какой формулировкой
    'moderator_note', 'moderated_by', 'moderated_at',
])]
class ContactUnlock extends Model
{
    /** @use HasFactory<ContactUnlockFactory> */
    use HasFactory;

    /** Воронка работы с контактом. Подписи — те же, что в интерфейсе. */
    public const STATUSES = [
        'new' => 'Новый',
        'contacted' => 'Связался',
        'negotiating' => 'В переговорах',
        'deal' => 'Сделка',
        'rejected' => 'Не подошёл',
    ];

    protected function casts(): array
    {
        return ['complained_at' => 'datetime', 'refunded' => 'boolean', 'moderated_at' => 'datetime'];
    }

    public function company(): BelongsTo
    {
        return $this->belongsTo(Company::class);
    }

    public function targetCompany(): BelongsTo
    {
        return $this->belongsTo(Company::class, 'target_company_id');
    }

    /** Кто принял решение по обращению. */
    public function moderator(): BelongsTo
    {
        return $this->belongsTo(User::class, 'moderated_by');
    }

    public function listing(): BelongsTo
    {
        return $this->belongsTo(Listing::class);
    }

    public function review(): BelongsTo
    {
        return $this->belongsTo(Review::class, 'id', 'contact_unlock_id');
    }

    public function statusLabel(): string
    {
        return self::STATUSES[$this->status] ?? $this->status;
    }

    /**
     * Отзыв уместен только после сделки: оценка «не подошёл» от того,
     * кто не работал с компанией, — это не отзыв, а реакция на отказ.
     */
    public function canBeReviewed(): bool
    {
        return in_array($this->status, ['deal', 'negotiating'], true);
    }
}
