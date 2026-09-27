<?php

declare(strict_types=1);

namespace App\Models;

use Illuminate\Database\Eloquent\Attributes\Fillable;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\Relations\BelongsTo;

/**
 * Отзыв пользователя о самой площадке SavdEx.
 *
 * В отличие от Review — не о компании и не влияет ни на чей рейтинг.
 * Пишет его только сам пользователь (кабинет, /reviews/new): заводить
 * отзывы о площадке вручную или загрузкой нельзя — витрина отзывов
 * должна состоять из слов настоящих людей.
 */
#[Fillable([
    'user_id', 'company_id', 'rating', 'rating_usability', 'rating_search', 'rating_support',
    'body', 'status', 'screening_flags', 'moderator_note', 'moderated_by', 'moderated_at',
])]
class PlatformReview extends Model
{
    public const STATUS_PUBLISHED = 'published';

    public const STATUS_MODERATION = 'moderation';

    public const STATUS_HIDDEN = 'hidden';

    /** Оценки по сторонам работы площадки: поле → ключ подписи в словаре. */
    public const CRITERIA = [
        'rating_usability' => 'usability',
        'rating_search' => 'search',
        'rating_support' => 'support',
    ];

    protected $attributes = [
        'status' => self::STATUS_MODERATION,
    ];

    protected function casts(): array
    {
        return ['moderated_at' => 'datetime'];
    }

    public function user(): BelongsTo
    {
        return $this->belongsTo(User::class);
    }

    public function company(): BelongsTo
    {
        return $this->belongsTo(Company::class);
    }

    public function moderator(): BelongsTo
    {
        return $this->belongsTo(User::class, 'moderated_by');
    }

    /**
     * Подписи критериев на языке посетителя.
     *
     * @return array<string, string>
     */
    public static function criteriaLabels(?string $locale = null): array
    {
        return array_map(
            fn (string $key): string => __('ui.platform_reviews.criteria.'.$key, locale: $locale),
            self::CRITERIA,
        );
    }
}
