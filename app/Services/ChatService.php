<?php

declare(strict_types=1);

namespace App\Services;

use App\Exceptions\ChatRejected;
use App\Models\Company;
use App\Models\ItTask;
use App\Models\Listing;
use App\Models\Message;
use App\Models\MessageThread;
use App\Models\User;
use App\Models\Wallet;
use App\Support\Notifier;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Str;

/**
 * Чат между компаниями: отклики на объявления и переписка.
 *
 * Отклик — платное действие тарифа (responses_limit, «откликов
 * в месяц» на витрине тарифов): списывается один отклик за НОВЫЙ
 * разговор, сами сообщения внутри разговора бесплатны. Иначе лимит
 * наказывал бы за живое общение, а не за охват.
 *
 * Контакты в тексте маскируются: телефоны, почта и ссылки передаются
 * только через раскрытие контактов — чат не должен быть бесплатным
 * обходом ядра монетизации (§3.2 ТЗ), ровно как и описания объявлений.
 */
class ChatService
{
    /** Сообщение длиннее не принимается — это уже документ, а не реплика. */
    public const MAX_LENGTH = 2000;

    public function __construct(private readonly Notifier $notifier) {}

    /**
     * Отклик на объявление: новый разговор или продолжение начатого.
     *
     * @throws ChatRejected причина отказа — в сообщении, её видит человек
     */
    public function respond(Listing $listing, Company $company, User $user, string $text): MessageThread
    {
        $seller = $listing->company;

        if ($seller === null) {
            throw new ChatRejected(__('ui.messages.chat.listing_gone'));
        }

        if ($seller->id === $company->id) {
            throw new ChatRejected(__('ui.messages.chat.own_listing'));
        }

        if ($listing->status !== Listing::STATUS_ACTIVE) {
            throw new ChatRejected(__('ui.messages.chat.listing_off'));
        }

        return DB::transaction(function () use ($listing, $seller, $company, $user, $text): MessageThread {
            $thread = MessageThread::query()
                ->where('listing_id', $listing->id)
                ->where('buyer_company_id', $company->id)
                ->first();

            // Повторный отклик продолжает разговор и лимит не тратит
            if ($thread === null) {
                $this->spendResponse($company);

                $thread = MessageThread::create([
                    'listing_id' => $listing->id,
                    'buyer_company_id' => $company->id,
                    'seller_company_id' => $seller->id,
                ]);
            }

            $this->send($thread, $company, $user, $text);

            return $thread;
        });
    }

    /**
     * Отклик IT-исполнителя на IT-задачу: новый разговор или продолжение.
     *
     * Та же квота откликов, что и у объявлений: списывается за новый
     * разговор. Откликаться могут только компании с ролью IT-исполнителя —
     * иначе раздел превратился бы в ещё один канал спама заказчикам.
     *
     * @throws ChatRejected
     */
    public function respondToTask(ItTask $task, Company $company, User $user, string $text): MessageThread
    {
        $customer = $task->company;

        if ($customer === null) {
            throw new ChatRejected(__('ui.messages.chat.task_gone'));
        }

        if ($customer->id === $company->id) {
            throw new ChatRejected(__('ui.messages.chat.own_task'));
        }

        if (! $task->isActive()) {
            throw new ChatRejected(__('ui.messages.chat.task_closed'));
        }

        if (! $company->is_it_provider) {
            throw new ChatRejected(__('ui.messages.chat.it_role_needed'));
        }

        return DB::transaction(function () use ($task, $customer, $company, $user, $text): MessageThread {
            $thread = MessageThread::query()
                ->where('it_task_id', $task->id)
                ->where('buyer_company_id', $company->id)
                ->first();

            if ($thread === null) {
                $this->spendResponse($company);

                $thread = MessageThread::create([
                    'it_task_id' => $task->id,
                    'buyer_company_id' => $company->id,
                    'seller_company_id' => $customer->id,
                ]);

                $task->increment('responses_count');
            }

            $this->send($thread, $company, $user, $text);

            return $thread;
        });
    }

    /**
     * Сообщение в разговор. Отправитель обязан быть его стороной.
     *
     * @throws ChatRejected
     */
    public function send(MessageThread $thread, Company $company, User $user, string $text): Message
    {
        if (! $thread->isParticipant($company)) {
            throw new ChatRejected(__('ui.messages.chat.not_yours'));
        }

        $body = self::maskContacts(trim($text));

        if ($body === '') {
            throw new ChatRejected(__('ui.messages.chat.body_required'));
        }

        $recipient = $thread->counterpart($company);

        // До записи: было ли у получателя непрочитанное. Уведомление
        // шлём только на первое — иначе десять реплик подряд дают
        // десять уведомлений об одном и том же разговоре
        $hadUnread = $recipient !== null && $thread->unreadCountFor($recipient) > 0;

        $message = Message::create([
            'thread_id' => $thread->id,
            'company_id' => $company->id,
            'user_id' => $user->id,
            'body' => Str::limit($body, self::MAX_LENGTH, ''),
        ]);

        $thread->forceFill(['last_message_at' => now()])->save();
        $thread->markReadFor($company);

        if ($recipient !== null && ! $hadUnread) {
            $this->notifier->company(
                $recipient,
                'chat',
                "Новое сообщение от «{$company->name}»",
                [
                    'body' => Str::limit($body, 120),
                    'url' => "/cabinet/chats/{$thread->id}",
                ],
            );
        }

        return $message;
    }

    /**
     * Хватает ли компании лимита откликов — и списание одного.
     *
     * Условный UPDATE, а не проверка с записью: lockForUpdate на SQLite
     * ничего не блокирует (см. PromoCodeService::capture), и два
     * одновременных отклика прошли бы один и тот же остаток.
     *
     * @throws ChatRejected
     */
    private function spendResponse(Company $company): void
    {
        $limit = $company->plan()->responses_limit;

        if ($limit === null) {
            return; // безлимит
        }

        if ($limit < 1) {
            throw new ChatRejected(__('ui.messages.chat.plan_no_replies'));
        }

        $wallet = Wallet::firstOrCreate(['company_id' => $company->id]);

        $spent = Wallet::query()
            ->where('id', $wallet->id)
            ->where('responses_used_this_period', '<', $limit)
            ->increment('responses_used_this_period');

        if ($spent !== 1) {
            throw new ChatRejected(__('ui.messages.chat.replies_used_up', ['limit' => $limit]));
        }
    }

    /**
     * Метка на месте скрытого контакта.
     *
     * Не слово, а многоточие: подстановка попадает в текст сообщения
     * и хранится в базе, а читает его собеседник — возможно, на другом
     * языке. «[скрыто]» он бы не понял, «[•••]» читается одинаково.
     */
    public const MASK = '[•••]';

    /**
     * Маскировка контактов в тексте сообщения.
     *
     * Те же приметы, что ловит ReviewScreening: почта, ссылки и телеграм-
     * никнеймы, телефонные последовательности. Порог в девять цифр не
     * трогает цены («1 200 000» — семь цифр), но накрывает узбекские
     * номера с кодом и без.
     */
    public static function maskContacts(string $text): string
    {
        $masked = preg_replace('/[\w.+-]+@[\w-]+\.[a-z]{2,}/iu', self::MASK, $text);
        $masked = preg_replace('#(?:https?://|www\.|t\.me/)\S+#iu', self::MASK, (string) $masked);
        $masked = preg_replace('/(?<![\w.])@[a-z0-9_]{4,}/iu', self::MASK, (string) $masked);

        // Телефон: девять и больше цифр подряд с учётом пробелов и скобок
        $masked = preg_replace_callback(
            '/\+?[\d(][\d\s()-]{6,}\d/u',
            fn (array $m): string => preg_match_all('/\d/', $m[0]) >= 9 ? self::MASK : $m[0],
            (string) $masked,
        );

        return (string) $masked;
    }
}
