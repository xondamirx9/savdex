<?php

declare(strict_types=1);

namespace App\Services;

use App\Models\PlatformReview;
use App\Models\User;
use App\Support\AdminLog;
use App\Support\Notifier;
use App\Support\ReviewScreening;

/**
 * Отзывы о площадке: кто может написать, сохранение, модерация.
 *
 * Правила те же, что у отзывов о компаниях, где они применимы:
 * подтверждённая почта, живая учётная запись, проверка текста на
 * контакты и брань, премодерация по той же настройке. Раскрытия
 * контактов не нужно — оценивают площадку, а не сделку.
 */
class PlatformReviewService
{
    public const MIN_BODY = 30;

    public function __construct(private readonly Notifier $notifier) {}

    /** Почему пользователь не может оставить отзыв; null — может. */
    public function blockedReason(User $user): ?string
    {
        if (! $user->hasVerifiedEmail()) {
            return __('ui.messages.review.verify_email');
        }

        if ($user->status !== 'active' || $user->company?->isBlocked()) {
            return __('ui.messages.review.blocked');
        }

        return null;
    }

    public function mine(User $user): ?PlatformReview
    {
        return PlatformReview::query()->where('user_id', $user->id)->first();
    }

    /**
     * Сохранить отзыв: новый или правка своего.
     *
     * Правка возвращает отзыв на проверку так же, как новый: иначе
     * одобренный текст можно было бы заменить чем угодно.
     *
     * @param  array<string, mixed>  $data
     * @return array{ok: bool, message: string}
     */
    public function save(User $user, array $data): array
    {
        $reason = $this->blockedReason($user);

        if ($reason !== null) {
            return ['ok' => false, 'message' => $reason];
        }

        $body = trim((string) $data['body']);
        $flags = ReviewScreening::reasons($body);
        $needsReview = $flags !== [] || ReviewService::premoderationEnabled();

        PlatformReview::query()->updateOrCreate(
            ['user_id' => $user->id],
            [
                'company_id' => $user->company_id,
                'rating' => (int) $data['rating'],
                ...array_map(
                    fn (string $field): ?int => isset($data[$field]) && (int) $data[$field] > 0 ? (int) $data[$field] : null,
                    array_combine(array_keys(PlatformReview::CRITERIA), array_keys(PlatformReview::CRITERIA)),
                ),
                'body' => $body,
                'status' => $needsReview ? PlatformReview::STATUS_MODERATION : PlatformReview::STATUS_PUBLISHED,
                'screening_flags' => $flags === [] ? null : implode('; ', $flags),
                'moderator_note' => null,
                'moderated_by' => null,
                'moderated_at' => null,
            ],
        );

        if (! $needsReview) {
            return ['ok' => true, 'message' => __('ui.platform_reviews.published')];
        }

        return [
            'ok' => true,
            'message' => $flags === []
                ? __('ui.messages.review.sent_to_moderation')
                : __('ui.messages.review.sent_flagged', ['reason' => mb_strtolower($flags[0])]),
        ];
    }

    public function approve(PlatformReview $review, User $moderator): void
    {
        $this->decide($review, $moderator, PlatformReview::STATUS_PUBLISHED, null);

        if ($review->user !== null) {
            $this->notifier->user($review->user, 'review', __('ui.platform_reviews.notice_published', locale: $review->user->locale), [
                'tone' => 'success',
                'url' => '/reviews?type=platform',
            ]);
        }

        AdminLog::record('approved', 'reviews', $review, actor: $moderator);
    }

    /**
     * Отзыв не пропущен или снят с витрины.
     *
     * Автору — причина словами модератора: отзыв, исчезнувший молча,
     * читается как «площадка убирает неудобное».
     */
    public function reject(PlatformReview $review, User $moderator, string $note): void
    {
        $this->decide($review, $moderator, PlatformReview::STATUS_HIDDEN, $note);

        if ($review->user !== null) {
            $this->notifier->user($review->user, 'moderation', __('ui.platform_reviews.notice_rejected', locale: $review->user->locale), [
                'tone' => 'warning',
                'body' => $note,
                'url' => '/reviews/new',
            ]);
        }

        AdminLog::record('rejected', 'reviews', $review, note: $note, actor: $moderator);
    }

    /** Вернуть скрытый отзыв: решение бывает ошибочным. */
    public function restore(PlatformReview $review, User $moderator): void
    {
        $this->decide($review, $moderator, PlatformReview::STATUS_PUBLISHED, null);

        AdminLog::record('restored', 'reviews', $review, actor: $moderator);
    }

    private function decide(PlatformReview $review, User $moderator, string $status, ?string $note): void
    {
        $review->forceFill([
            'status' => $status,
            'moderator_note' => $note,
            'moderated_by' => $moderator->id,
            'moderated_at' => now(),
        ])->save();
    }

    /** @return array<string, list<string>> */
    public static function rules(): array
    {
        return [
            'rating' => ['required', 'integer', 'between:1,5'],
            'rating_usability' => ['nullable', 'integer', 'between:0,5'],
            'rating_search' => ['nullable', 'integer', 'between:0,5'],
            'rating_support' => ['nullable', 'integer', 'between:0,5'],
            'body' => ['required', 'string', 'min:'.self::MIN_BODY, 'max:2000'],
        ];
    }
}
