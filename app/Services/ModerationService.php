<?php

declare(strict_types=1);

namespace App\Services;

use App\Models\CompanyDocument;
use App\Models\ContactUnlock;
use App\Models\Review;
use App\Models\User;
use App\Support\Notifier;
use Illuminate\Support\Facades\DB;

/**
 * Решения модератора: споры по отзывам, жалобы на контакты, документы.
 *
 * Все три вида обращений раньше упирались в тупик: пользователь их
 * отправлял, статус ставился в pending — и на этом всё. Жалоба на
 * нерабочий контакт при этом сопровождается обещанием «вернём кредит»,
 * то есть невыполненным обязательством в деньгах.
 *
 * Логика вынесена из админки: решение меняет чужие данные, чужой
 * баланс и чужой рейтинг, и должно вести себя одинаково, откуда бы
 * его ни вызвали.
 */
class ModerationService
{
    public function __construct(
        private readonly Notifier $notifier,
        private readonly ReviewService $reviews,
    ) {}

    // ── Споры по отзывам ─────────────────────────────────────

    /**
     * Спор удовлетворён: отзыв скрыт с витрины.
     *
     * Не удалён — скрыт. Удаление стёрло бы и историю обращения,
     * и возможность вернуть отзыв, если решение окажется ошибочным.
     * Рейтинг пересчитывается сразу: скрытый отзыв не должен
     * продолжать тянуть оценку вниз.
     */
    public function acceptDispute(Review $review, User $moderator, string $note): void
    {
        DB::transaction(function () use ($review, $moderator, $note): void {
            $review->forceFill([
                'status' => 'hidden',
                'dispute_status' => 'accepted',
                'moderator_note' => $note,
                'moderated_by' => $moderator->id,
                'moderated_at' => now(),
            ])->save();

            $this->reviews->recalculate($review->company);
        });

        $this->notifier->company(
            $review->company,
            'moderation',
            'Спор по отзыву удовлетворён — отзыв скрыт',
            ['tone' => 'success', 'body' => $note, 'url' => '/cabinet/reviews'],
        );

        /*
         * Автора уведомляем тоже. Узнать, что твой отзыв сняли, от самой
         * площадки — неприятно, но честно; узнать случайно, зайдя на
         * визитку через месяц, — повод перестать ей доверять.
         */
        if ($review->authorCompany !== null) {
            $this->notifier->company(
                $review->authorCompany,
                'moderation',
                'Ваш отзыв скрыт по результатам проверки',
                ['tone' => 'warning', 'body' => $note],
            );
        }
    }

    /** Спор отклонён: отзыв остаётся, компания получает объяснение. */
    public function declineDispute(Review $review, User $moderator, string $note): void
    {
        $review->forceFill([
            'dispute_status' => 'declined',
            'moderator_note' => $note,
            'moderated_by' => $moderator->id,
            'moderated_at' => now(),
        ])->save();

        $this->notifier->company(
            $review->company,
            'moderation',
            'Спор по отзыву отклонён — отзыв остаётся',
            ['tone' => 'warning', 'body' => $note, 'url' => '/cabinet/reviews'],
        );
    }

    // ── Премодерация отзывов ─────────────────────────────────

    /**
     * Отзыв прошёл проверку и появляется на витрине.
     *
     * Уведомление компании уходит именно здесь, а не при создании:
     * пока отзыв ждёт модератора, компания его не видит и не должна
     * отвечать на то, что может быть и не опубликовано.
     */
    public function approveReview(Review $review, User $moderator): void
    {
        DB::transaction(function () use ($review, $moderator): void {
            $review->forceFill([
                'status' => Review::STATUS_PUBLISHED,
                'moderated_by' => $moderator->id,
                'moderated_at' => now(),
            ])->save();

            $this->reviews->recalculate($review->company);
        });

        if ($review->authorCompany !== null && $review->company !== null) {
            $this->reviews->publishedNotice($review, $review->authorCompany, $review->company);
        }
    }

    /**
     * Отзыв не пропущен.
     *
     * Автору объясняем причину: отзыв, исчезнувший молча, читается как
     * «площадка убирает неудобное» — ровно то обвинение, ради защиты
     * от которого премодерация и вводилась.
     */
    public function rejectReview(Review $review, User $moderator, string $note): void
    {
        DB::transaction(function () use ($review, $moderator, $note): void {
            $review->forceFill([
                'status' => Review::STATUS_HIDDEN,
                'moderator_note' => $note,
                'moderated_by' => $moderator->id,
                'moderated_at' => now(),
            ])->save();

            $this->reviews->recalculate($review->company);
        });

        if ($review->authorCompany !== null) {
            $this->notifier->company(
                $review->authorCompany,
                'moderation',
                'Ваш отзыв не прошёл проверку',
                ['tone' => 'warning', 'body' => $note],
            );
        }
    }

    /** Вернуть скрытый отзыв на витрину: решение бывает ошибочным. */
    public function restoreReview(Review $review, User $moderator): void
    {
        DB::transaction(function () use ($review, $moderator): void {
            $review->forceFill([
                'status' => 'published',
                'dispute_status' => 'declined',
                'moderated_by' => $moderator->id,
                'moderated_at' => now(),
            ])->save();

            $this->reviews->recalculate($review->company);
        });
    }

    // ── Жалобы на контакты ───────────────────────────────────

    /**
     * Жалоба признана обоснованной — возвращаем потраченное.
     *
     * Что именно вернуть, зависит от того, чем платили. Кредит —
     * начислением на кошелёк с записью в журнал. Контакт из месячного
     * лимита тарифа — уменьшением счётчика израсходованных: начислять
     * за него кредит значит выдавать больше, чем было списано.
     *
     * Само раскрытие остаётся: показанные контакты обратно не забрать,
     * и делать вид, что покупатель их не видел, бессмысленно.
     */
    public function acceptComplaint(ContactUnlock $unlock, User $moderator, string $note): void
    {
        DB::transaction(function () use ($unlock, $moderator, $note): void {
            $wallet = $unlock->company?->wallet;

            if ($wallet !== null && ! $unlock->refunded) {
                if ($unlock->credits_spent > 0) {
                    $wallet->grant('credits', $unlock->credits_spent, 'complaint_refund', $unlock, $moderator->id);
                } elseif ($wallet->contacts_used_this_period > 0) {
                    $wallet->decrement('contacts_used_this_period');
                }
            }

            $unlock->forceFill([
                'complaint_status' => 'accepted',
                'refunded' => true,
                'moderator_note' => $note,
                'moderated_by' => $moderator->id,
                'moderated_at' => now(),
            ])->save();
        });

        if ($unlock->company !== null) {
            $this->notifier->company(
                $unlock->company,
                'moderation',
                'Жалоба на контакт подтверждена — потраченное вернули',
                ['tone' => 'success', 'body' => $note, 'url' => '/cabinet/contacts'],
            );
        }
    }

    /** Жалоба отклонена: возврата нет, но причина названа. */
    public function declineComplaint(ContactUnlock $unlock, User $moderator, string $note): void
    {
        $unlock->forceFill([
            'complaint_status' => 'declined',
            'moderator_note' => $note,
            'moderated_by' => $moderator->id,
            'moderated_at' => now(),
        ])->save();

        if ($unlock->company !== null) {
            $this->notifier->company(
                $unlock->company,
                'moderation',
                'Жалоба на контакт отклонена',
                ['tone' => 'warning', 'body' => $note, 'url' => '/cabinet/contacts'],
            );
        }
    }

    // ── Документы ────────────────────────────────────────────

    /**
     * Документ одобрен.
     *
     * Уровень верификации при этом не меняется: «Проверена» выдаётся
     * отдельным решением по совокупности документов, а не автоматически
     * за каждую загруженную бумагу. Иначе бейдж, обещанный витриной
     * как результат проверки, выдавала бы загрузка файла.
     */
    public function approveDocument(CompanyDocument $document, User $moderator): void
    {
        $document->forceFill([
            'moderation_status' => CompanyDocument::STATUS_APPROVED,
            'moderation_note' => null,
            'moderated_by' => $moderator->id,
            'moderated_at' => now(),
        ])->save();

        $this->notifier->company(
            $document->company,
            'moderation',
            "Документ «{$document->title}» принят",
            ['tone' => 'success', 'url' => '/cabinet/company'],
        );
    }

    /** Документ отклонён: без причины человек пришлёт тот же файл. */
    public function rejectDocument(CompanyDocument $document, User $moderator, string $reason): void
    {
        $document->forceFill([
            'moderation_status' => CompanyDocument::STATUS_REJECTED,
            'moderation_note' => $reason,
            'moderated_by' => $moderator->id,
            'moderated_at' => now(),
        ])->save();

        $this->notifier->company(
            $document->company,
            'moderation',
            "Документ «{$document->title}» отклонён",
            ['tone' => 'danger', 'body' => $reason, 'url' => '/cabinet/company'],
        );
    }
}
