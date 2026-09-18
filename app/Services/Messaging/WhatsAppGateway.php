<?php

declare(strict_types=1);

namespace App\Services\Messaging;

use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Log;

/**
 * WhatsApp Business (Meta Cloud API).
 *
 * Написать человеку первым можно только утверждённым шаблоном: вне
 * суточного окна переписки Meta свободный текст не пропускает. Шаблон
 * заводится в кабинете WhatsApp Business, категория «Аутентификация»,
 * с одной переменной — в неё подставляется ссылка на смену пароля.
 *
 * Пока в настройках нет токена и номера отправителя, способ не
 * показывается на форме восстановления: кнопка, которая ничего
 * не отправляет, хуже её отсутствия.
 */
class WhatsAppGateway
{
    private const TIMEOUT = 8;

    public function configured(): bool
    {
        return $this->token() !== '' && $this->phoneNumberId() !== '';
    }

    public function token(): string
    {
        return trim((string) config('services.whatsapp.token'));
    }

    public function phoneNumberId(): string
    {
        return trim((string) config('services.whatsapp.phone_number_id'));
    }

    /**
     * Шаблонное сообщение с одной переменной.
     *
     * @param  string  $phone  номер в любом виде: лишние символы уберём
     * @param  string  $value  что подставить в шаблон
     */
    public function send(string $phone, string $value, string $locale = 'ru'): bool
    {
        $to = preg_replace('/\D+/', '', $phone) ?? '';

        if (! $this->configured() || strlen($to) < 9) {
            return false;
        }

        $url = sprintf(
            'https://graph.facebook.com/%s/%s/messages',
            trim((string) config('services.whatsapp.api_version', 'v21.0')),
            $this->phoneNumberId(),
        );

        try {
            $response = Http::timeout(self::TIMEOUT)
                ->withToken($this->token())
                ->post($url, [
                    'messaging_product' => 'whatsapp',
                    'to' => $to,
                    'type' => 'template',
                    'template' => [
                        'name' => trim((string) config('services.whatsapp.template', 'password_reset')),
                        'language' => ['code' => $locale],
                        'components' => [[
                            'type' => 'body',
                            'parameters' => [['type' => 'text', 'text' => $value]],
                        ]],
                    ],
                ]);

            if ($response->successful()) {
                return true;
            }

            Log::warning('whatsapp.send_failed', ['status' => $response->status(), 'body' => $response->body()]);
        } catch (\Throwable $e) {
            Log::warning('whatsapp.send_error', ['error' => $e->getMessage()]);
        }

        return false;
    }
}
