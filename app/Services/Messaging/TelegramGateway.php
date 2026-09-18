<?php

declare(strict_types=1);

namespace App\Services\Messaging;

use App\Models\User;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

/**
 * Бот Telegram: привязка аккаунта и отправка сообщений.
 *
 * Бот не пишет первым — так устроен Telegram. Пока человек не нажал
 * «Старт» у бота площадки, его чат нам неизвестен, и отправить туда
 * нечего. Поэтому привязка идёт в одну сторону: кабинет показывает
 * ссылку вида t.me/бот?start=токен, человек открывает её и жмёт
 * «Старт», бот присылает нам номер чата, и мы запоминаем его
 * у пользователя.
 *
 * Токен привязки живёт четверть часа и лежит в кэше, а не в базе:
 * это одноразовый пропуск, а не свойство пользователя.
 */
class TelegramGateway
{
    private const LINK_TTL_MINUTES = 15;

    private const CACHE_PREFIX = 'telegram.link.';

    /** Telegram обрывает запрос сам; ждать дольше незачем. */
    private const TIMEOUT = 8;

    public function configured(): bool
    {
        return $this->token() !== '' && $this->botUsername() !== '';
    }

    public function token(): string
    {
        return trim((string) config('services.telegram.bot_token'));
    }

    public function botUsername(): string
    {
        return ltrim(trim((string) config('services.telegram.bot_username')), '@');
    }

    /**
     * Ссылка привязки для этого пользователя.
     *
     * Токен случайный и одноразовый: по нему бот узнаёт, к какой
     * учётной записи привязать чат. Пересылать такую ссылку нельзя —
     * тот, кто откроет её первым, привяжет свой Telegram к чужому
     * аккаунту, поэтому она и живёт пятнадцать минут.
     */
    public function linkUrl(User $user): string
    {
        $token = Str::random(32);

        Cache::put(self::CACHE_PREFIX.$token, $user->id, now()->addMinutes(self::LINK_TTL_MINUTES));

        return 'https://t.me/'.$this->botUsername().'?start='.$token;
    }

    /** Пользователь, которому принадлежит токен привязки; null — токен истёк. */
    public function claim(string $token): ?User
    {
        $key = self::CACHE_PREFIX.$token;
        $userId = Cache::get($key);

        if ($userId === null) {
            return null;
        }

        // Токен одноразовый: второй «Старт» по той же ссылке ничего
        // не привяжет, даже если ссылку кому-то переслали
        Cache::forget($key);

        return User::query()->find($userId);
    }

    /**
     * Сообщение в чат. false — не отправлено; причину пишем в лог,
     * наверх она не уходит: человеку на форме её знать незачем.
     */
    public function send(string $chatId, string $text): bool
    {
        if (! $this->configured() || trim($chatId) === '') {
            return false;
        }

        try {
            $response = Http::timeout(self::TIMEOUT)
                ->post('https://api.telegram.org/bot'.$this->token().'/sendMessage', [
                    'chat_id' => $chatId,
                    'text' => $text,
                    // Разметку не включаем: в текст попадает ссылка
                    // и имя площадки, и одна случайная звёздочка
                    // превратила бы сообщение в ошибку разбора
                    'disable_web_page_preview' => true,
                ]);

            if ($response->successful()) {
                return true;
            }

            Log::warning('telegram.send_failed', ['status' => $response->status(), 'body' => $response->body()]);
        } catch (\Throwable $e) {
            Log::warning('telegram.send_error', ['error' => $e->getMessage()]);
        }

        return false;
    }
}
