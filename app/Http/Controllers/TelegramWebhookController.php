<?php

declare(strict_types=1);

namespace App\Http\Controllers;

use App\Services\Messaging\TelegramGateway;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

/**
 * Что бот получает от Telegram.
 *
 * Нужна одна команда — «/start токен»: по ней бот узнаёт, к какой
 * учётной записи привязать этот чат. Всё остальное, что человек
 * напишет боту, вежливо игнорируется: бот площадки не переписка
 * с поддержкой, а способ доставки.
 *
 * Адрес содержит секрет из настроек: без него написать «/start
 * чужой-токен» мог бы кто угодно, кто знает адрес площадки.
 */
class TelegramWebhookController extends Controller
{
    public function __invoke(Request $request, string $secret, TelegramGateway $telegram): Response
    {
        $expected = trim((string) config('services.telegram.webhook_secret'));

        if ($expected === '' || ! hash_equals($expected, $secret)) {
            abort(404);
        }

        $message = (array) $request->input('message', []);
        $chatId = (string) data_get($message, 'chat.id', '');
        $text = trim((string) data_get($message, 'text', ''));

        if ($chatId === '' || ! str_starts_with($text, '/start')) {
            // Пустой ответ с кодом 200: Telegram повторяет доставку,
            // пока не получит его, и на «спасибо» от человека бот
            // ушёл бы в бесконечный круг повторов
            return response()->noContent();
        }

        $token = trim(mb_substr($text, strlen('/start')));
        $user = $token === '' ? null : $telegram->claim($token);

        if ($user === null) {
            $telegram->send($chatId, __('ui.messages.auth.telegram_link_expired'));

            return response()->noContent();
        }

        $user->forceFill([
            'telegram_chat_id' => $chatId,
            'telegram_username' => (string) data_get($message, 'from.username') ?: null,
            'telegram_linked_at' => now(),
        ])->save();

        $telegram->send($chatId, __('ui.messages.auth.telegram_linked', ['name' => $user->name]));

        return response()->noContent();
    }
}
