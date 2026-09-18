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

    public function webhookSecret(): string
    {
        return trim((string) config('services.telegram.webhook_secret'));
    }

    /** Адрес, на который Telegram присылает сообщения боту. */
    public function webhookUrl(): ?string
    {
        $secret = $this->webhookSecret();

        return $secret === '' ? null : url('/telegram/webhook/'.$secret);
    }

    /**
     * Зарегистрировать адрес у Telegram.
     *
     * Токен и секрет берутся из настроек, а не набираются руками:
     * подставлять их в адрес самому — это ровно тот случай, когда
     * в строку уезжает «<ТОКЕН>» и Telegram отвечает «Not Found».
     *
     * @return array{ok: bool, message: string}
     */
    public function registerWebhook(): array
    {
        $url = $this->webhookUrl();

        if (! $this->configured() || $url === null) {
            return ['ok' => false, 'message' => 'Не заданы TELEGRAM_BOT_TOKEN, TELEGRAM_BOT_USERNAME или TELEGRAM_WEBHOOK_SECRET.'];
        }

        return $this->call('setWebhook', ['url' => $url, 'drop_pending_updates' => true]);
    }

    /** @return array{ok: bool, message: string} */
    public function deleteWebhook(): array
    {
        return $this->configured()
            ? $this->call('deleteWebhook', [])
            : ['ok' => false, 'message' => 'Не задан TELEGRAM_BOT_TOKEN.'];
    }

    /**
     * Что Telegram знает о боте прямо сейчас: адрес, очередь
     * недоставленного и последняя ошибка доставки.
     *
     * @return array<string, mixed>|null
     */
    public function webhookInfo(): ?array
    {
        if (! $this->configured()) {
            return null;
        }

        try {
            $response = Http::timeout(self::TIMEOUT)->get($this->api('getWebhookInfo'));
        } catch (\Throwable) {
            return null;
        }

        return $response->successful() ? (array) $response->json('result') : null;
    }

    /**
     * Вызов метода Bot API с понятным ответом.
     *
     * @param  array<string, mixed>  $payload
     * @return array{ok: bool, message: string}
     */
    private function call(string $method, array $payload): array
    {
        try {
            $response = Http::timeout(self::TIMEOUT)->post($this->api($method), $payload);
        } catch (\Throwable $e) {
            return ['ok' => false, 'message' => $e->getMessage()];
        }

        if ($response->successful() && $response->json('ok') === true) {
            return ['ok' => true, 'message' => (string) ($response->json('description') ?? 'Готово')];
        }

        /*
         * 404 от Telegram означает ровно одно: такого бота нет —
         * в адрес уехал не тот токен. Говорим об этом прямо: само
         * «Not Found» человек читает как «сайт недоступен».
         */
        $description = (string) ($response->json('description') ?? $response->body());

        if ($response->status() === 404) {
            $description = 'Telegram не знает такого бота — проверьте TELEGRAM_BOT_TOKEN.';
        }

        return ['ok' => false, 'message' => $description];
    }

    private function api(string $method): string
    {
        return 'https://api.telegram.org/bot'.$this->token().'/'.$method;
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
                ->post($this->api('sendMessage'), [
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
