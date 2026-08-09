<?php

declare(strict_types=1);

namespace App\Services;

use App\Models\Company;
use App\Models\ContactUnlock;
use App\Models\Review;
use App\Models\Setting;
use App\Models\User;
use App\Support\Notifier;
use App\Support\ReviewScreening;
use Illuminate\Database\UniqueConstraintViolationException;
use Illuminate\Support\Facades\DB;

/**
 * Отзывы о компаниях.
 *
 * Оставить отзыв может только тот, кто оплатил раскрытие контактов
 * этой компании. Это единственное, что отделяет рейтинг площадки от
 * рейтинга, который накручивается за вечер: контакт стоит денег, и
 * отзыв за отзывом обходится дороже, чем стоит испорченная репутация
 * конкурента. Обещание вынесено на витрину и держится здесь.
 *
 * Пересчёт рейтинга делается сразу, а не ночным заданием: человек,
 * оставивший отзыв, должен увидеть результат, а не «завтра посчитаем».
 */
class ReviewService
{
    /** Ниже этой длины отзыв не помогает читающему. */
    private const MIN_BODY = 30;

    /** Вес среднего по площадке — как в ratings:recalculate. */
    private const WEIGHT = 5;

    public function __construct(private readonly Notifier $notifier) {}

    /**
     * Почему компания не может оставить отзыв. null — может.
     *
     * Отдельным методом, чтобы витрина показывала причину до нажатия,
     * а не отвечала отказом после.
     */
    public function blockedReason(?User $user, Company $target): ?string
    {
        $author = $user?->company;

        if ($author === null) {
            return 'Отзывы оставляют от имени компании — заполните её данные в кабинете.';
        }

        if ($author->id === $target->id) {
            return 'Это ваша компания.';
        }

        if (! $user->hasVerifiedEmail()) {
            return 'Подтвердите почту, чтобы оставлять отзывы.';
        }

        if ($author->isBlocked() || $user->status !== 'active') {
            return 'Ваша учётная запись заблокирована.';
        }

        if (! $this->unlock($author, $target)) {
            return 'Отзыв можно оставить только после раскрытия контактов: так на площадке нет отзывов от тех, кто с компанией не работал.';
        }

        $existing = $this->existing($author, $target);

        if ($existing !== null) {
            /*
             * Отзыв на проверке автор на витрине не видит — своего
             * текста там нет. Без этой строки он читает «вы уже
             * оставляли отзыв» и не понимает, куда тот делся.
             */
            return match ($existing->status) {
                Review::STATUS_MODERATION => 'Ваш отзыв на проверке — он появится здесь, когда модератор его посмотрит.',
                Review::STATUS_HIDDEN => 'Ваш отзыв не прошёл проверку. Причина — в уведомлениях.',
                default => 'Вы уже оставляли отзыв этой компании.',
            };
        }

        return null;
    }

    private function unlock(Company $author, Company $target): ?ContactUnlock
    {
        return ContactUnlock::query()
            ->where('company_id', $author->id)
            ->where('target_company_id', $target->id)
            ->first();
    }

    private function existing(Company $author, Company $target): ?Review
    {
        return Review::query()
            ->where('company_id', $target->id)
            ->where('author_company_id', $author->id)
            ->whereNull('listing_id')
            ->first();
    }

    /**
     * Создать отзыв.
     *
     * @param  array<string, mixed>  $data
     * @return array{ok: bool, message: string, review: Review|null}
     */
    public function create(User $user, Company $target, array $data): array
    {
        $reason = $this->blockedReason($user, $target);

        if ($reason !== null) {
            return ['ok' => false, 'message' => $reason, 'review' => null];
        }

        $author = $user->company;
        $unlock = $this->unlock($author, $target);
        $body = trim((string) $data['body']);

        /*
         * Отзыв либо публикуется сразу, либо ждёт модератора.
         *
         * Ждёт в двух случаях: включена премодерация или сработала
         * автоматическая проверка. Второе не отключается настройкой —
         * контакты в тексте раздают бесплатно то, что продаётся
         * за кредиты, и пускать такое на витрину нельзя ни при каких
         * настройках площадки.
         */
        $flags = ReviewScreening::reasons($body);
        $needsReview = $flags !== [] || self::premoderationEnabled();

        try {
            $review = DB::transaction(function () use ($author, $target, $user, $unlock, $data, $body, $needsReview, $flags): Review {
                $review = Review::create([
                    'company_id' => $target->id,
                    'author_company_id' => $author->id,
                    'author_user_id' => $user->id,
                    'contact_unlock_id' => $unlock?->id,
                    'listing_id' => null,
                    'rating' => (int) $data['rating'],
                    'rating_description' => $data['rating_description'] ?? null,
                    'rating_response' => $data['rating_response'] ?? null,
                    'rating_deadlines' => $data['rating_deadlines'] ?? null,
                    'rating_quality' => $data['rating_quality'] ?? null,
                    'body' => $body,
                    'deal_confirmed' => (bool) ($data['deal_confirmed'] ?? false),
                    'status' => $needsReview ? Review::STATUS_MODERATION : Review::STATUS_PUBLISHED,
                    // Что именно насторожило — видно модератору сразу,
                    // без перечитывания текста в поисках причины
                    'screening_flags' => $flags === [] ? null : implode('; ', $flags),
                ]);

                $this->recalculate($target);

                return $review;
            });
        } catch (UniqueConstraintViolationException) {
            // Двойное нажатие или второй запрос параллельно: обещание
            // «один отзыв на компанию» держит уникальный индекс
            return ['ok' => false, 'message' => 'Вы уже оставляли отзыв этой компании.', 'review' => null];
        }

        if ($needsReview) {
            return [
                'ok' => true,
                'message' => $flags === []
                    ? 'Отзыв отправлен на проверку. Обычно она занимает несколько часов — после этого отзыв появится на странице компании.'
                    : 'Отзыв отправлен на проверку: '.mb_strtolower($flags[0]).'. Модератор посмотрит его вручную.',
                'review' => $review,
            ];
        }

        $this->publishedNotice($review, $author, $target);

        return [
            'ok' => true,
            'message' => 'Отзыв опубликован. Компания получила уведомление и сможет ответить.',
            'review' => $review,
        ];
    }

    /**
     * Уведомление компании о новом отзыве.
     *
     * Отправляется в момент появления на витрине, а не создания:
     * отзыв, ждущий модератора, компания видеть не должна — иначе она
     * успеет ответить на то, что может и не быть опубликовано.
     */
    public function publishedNotice(Review $review, Company $author, Company $target): void
    {
        $this->notifier->company(
            $target,
            'review',
            "Компания «{$author->name}» оставила отзыв: {$review->rating} из 5",
            [
                'tone' => $review->rating >= 4 ? 'success' : 'warning',
                'body' => str($review->body)->limit(140)->toString(),
                'url' => '/cabinet/reviews',
            ],
        );
    }

    /** Включена ли проверка каждого отзыва перед публикацией. */
    public static function premoderationEnabled(): bool
    {
        return (bool) Setting::get('reviews_premoderation', true);
    }

    /**
     * Байесовский рейтинг компании.
     *
     * Та же формула, что в ratings:recalculate: среднее арифметическое
     * ставило бы компанию с одним отзывом на пять звёзд выше компании
     * с сотней отзывов и средним 4,8. Ночной пересчёт остаётся —
     * он выравнивает всех при изменении среднего по площадке.
     */
    public function recalculate(Company $company): void
    {
        $globalAverage = (float) Review::query()->where('status', 'published')->avg('rating') ?: 4.0;

        $row = Review::query()
            ->where('company_id', $company->id)
            ->where('status', 'published')
            ->selectRaw('COUNT(*) as total, SUM(rating) as sum_rating')
            ->first();

        $count = (int) ($row->total ?? 0);
        $sum = (float) ($row->sum_rating ?? 0);

        $company->forceFill([
            'rating' => $count > 0
                ? round((self::WEIGHT * $globalAverage + $sum) / (self::WEIGHT + $count), 2)
                : 0.0,
            'reviews_count' => $count,
        ])->save();
    }

    /** @return array<string, string> */
    public static function rules(): array
    {
        return [
            'rating' => ['required', 'integer', 'between:1,5'],
            'rating_description' => ['nullable', 'integer', 'between:1,5'],
            'rating_response' => ['nullable', 'integer', 'between:1,5'],
            'rating_deadlines' => ['nullable', 'integer', 'between:1,5'],
            'rating_quality' => ['nullable', 'integer', 'between:1,5'],
            'body' => ['required', 'string', 'min:'.self::MIN_BODY, 'max:2000'],
            'deal_confirmed' => ['boolean'],
        ];
    }

    /** @return array<string, string> */
    public static function messages(): array
    {
        return [
            'rating.required' => 'Поставьте общую оценку',
            'body.required' => 'Напишите, как прошла работа',
            'body.min' => 'Отзыв в пару слов ничего не говорит следующему покупателю — опишите, что было хорошо и что нет',
        ];
    }
}
