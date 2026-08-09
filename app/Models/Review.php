<?php

declare(strict_types=1);

namespace App\Models;

use Database\Factories\ReviewFactory;
use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Factories\HasFactory;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * Отзыв о компании.
 *
 * Оставить его может только тот, кто оплатил раскрытие контактов —
 * отсюда связь с ContactUnlock. Накрутить рейтинг, не заплатив,
 * невозможно; это обещание вынесено на витрину.
 */
#[Fillable([
    'company_id', 'author_company_id', 'author_user_id', 'contact_unlock_id', 'listing_id',
    'rating', 'rating_description', 'rating_response', 'rating_deadlines', 'rating_quality',
    'body', 'deal_confirmed', 'reply', 'replied_at', 'dispute_status', 'dispute_reason', 'status', 'screening_flags',
    // След решения модератора: кто, когда и с какой формулировкой
    'moderator_note', 'moderated_by', 'moderated_at',
])]
class Review extends Model
{
    /** @use HasFactory<ReviewFactory> */
    use HasFactory;

    /** Отзыв виден на витрине и участвует в рейтинге. */
    public const STATUS_PUBLISHED = 'published';

    /** Ждёт проверки модератора: в рейтинг и на витрину не попадает. */
    public const STATUS_MODERATION = 'moderation';

    /** Снят по итогам спора или проверки. */
    public const STATUS_HIDDEN = 'hidden';

    /** Критерии оценки. Ключ — колонка, значение — подпись в интерфейсе. */
    public const CRITERIA = [
        'rating_description' => 'Соответствие описанию',
        'rating_response' => 'Скорость ответа',
        'rating_deadlines' => 'Соблюдение сроков',
        'rating_quality' => 'Качество товара',
    ];

    protected function casts(): array
    {
        return ['deal_confirmed' => 'boolean', 'replied_at' => 'datetime', 'moderated_at' => 'datetime'];
    }

    public function company(): BelongsTo
    {
        return $this->belongsTo(Company::class);
    }

    public function authorCompany(): BelongsTo
    {
        return $this->belongsTo(Company::class, 'author_company_id');
    }

    public function listing(): BelongsTo
    {
        return $this->belongsTo(Listing::class);
    }

    /** Кто принял решение по обращению. */
    public function moderator(): BelongsTo
    {
        return $this->belongsTo(User::class, 'moderated_by');
    }

    public function hasReply(): bool
    {
        return filled($this->reply);
    }
}
