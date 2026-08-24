<?php

declare(strict_types=1);

namespace App\Services;

use App\Exceptions\ChatRejected;
use App\Models\Company;
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
            throw new ChatRejected('Объявление больше не доступно.');
        }

        if ($seller->id === $company->id) {
            throw new ChatRejected('Это ваше объявление — откликаться на него не нужно.');
        }

        if ($listing->status !== Listing::STATUS_ACTIVE) {
            throw new ChatRejected('Объявление снято с публикации — откликнуться нельзя.');
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
     * Сообщение в разговор. Отправитель обязан быть его стороной.
     *
     * @throws ChatRejected
     */
    public function send(MessageThread $thread, Company $company, User $user, string $text): Message
    {
        if (! $thread->isParticipant($company)) {
            throw new ChatRejected('Этот разговор принадлежит другим компаниям.');
        }

        $body = self::maskContacts(trim($text));

        if ($body === '') {
            throw new ChatRejected('Введите сообщение');
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
            throw new ChatRejected('Ваш тариф не включает отклики. Подключите платный тариф — и откликайтесь на предложения напрямую.');
        }

        $wallet = Wallet::firstOrCreate(['company_id' => $company->id]);

        $spent = Wallet::query()
            ->where('id', $wallet->id)
            ->where('responses_used_this_period', '<', $limit)
            ->increment('responses_used_this_period');

        if ($spent !== 1) {
            throw new ChatRejected("Лимит откликов на этот месяц исчерпан ({$limit}). Он обновится с началом нового периода, либо смените тариф.");
        }
    }

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
        $masked = preg_replace('/[\w.+-]+@[\w-]+\.[a-z]{2,}/iu', '[скрыто]', $text);
        $masked = preg_replace('#(?:https?://|www\.|t\.me/)\S+#iu', '[скрыто]', (string) $masked);
        $masked = preg_replace('/(?<![\w.])@[a-z0-9_]{4,}/iu', '[скрыто]', (string) $masked);

        // Телефон: девять и больше цифр подряд с учётом пробелов и скобок
        $masked = preg_replace_callback(
            '/\+?[\d(][\d\s()-]{6,}\d/u',
            fn (array $m): string => preg_match_all('/\d/', $m[0]) >= 9 ? '[скрыто]' : $m[0],
            (string) $masked,
        );

        return (string) $masked;
    }
}
