<?php

declare(strict_types=1);

namespace App\Services;

use App\Models\User;
use App\Services\Messaging\TelegramGateway;
use App\Services\Messaging\WhatsAppGateway;
use Illuminate\Support\Facades\Password;

/**
 * Куда прислать ссылку на смену пароля.
 *
 * Почта была единственным способом, и человек, потерявший доступ
 * к рабочему ящику (уволился сотрудник, который его заводил; домен
 * переехал), терял вместе с ним и учётную запись. Теперь ссылку можно
 * получить в Telegram или WhatsApp — туда, куда человек смотрит чаще,
 * чем в почту.
 *
 * Отправляется именно ссылка, а не пароль: паролей площадка не хранит
 * даже у себя — в базе лежит их необратимый отпечаток. Прислать пароль
 * невозможно, да и незачем: ссылка живёт час и работает один раз,
 * а пароль, отправленный сообщением, остаётся в переписке навсегда.
 */
class PasswordResetDelivery
{
    public const MAIL = 'mail';

    public const TELEGRAM = 'telegram';

    public const WHATSAPP = 'whatsapp';

    public function __construct(
        private readonly TelegramGateway $telegram,
        private readonly WhatsAppGateway $whatsapp,
    ) {}

    /**
     * Способы, которые площадка умеет прямо сейчас.
     *
     * Настроен только один — выбора на форме нет вовсе: переключатель
     * с единственным вариантом ничего не объясняет, а место занимает.
     *
     * @return list<string>
     */
    public function channels(): array
    {
        return array_values(array_filter([
            self::MAIL,
            $this->telegram->configured() ? self::TELEGRAM : null,
            $this->whatsapp->configured() ? self::WHATSAPP : null,
        ]));
    }

    public function supports(?string $channel): bool
    {
        return $channel !== null && in_array($channel, $this->channels(), true);
    }

    /**
     * Отправить ссылку выбранным способом.
     *
     * Возвращает признак «дошло» только для внутренних нужд: наружу
     * форма отвечает одинаково при любом исходе. Иначе по ответу
     * читается, зарегистрирован ли адрес и привязан ли у человека
     * Telegram, — и форма превращается в способ узнать это про чужую
     * компанию.
     */
    public function send(string $email, string $channel): bool
    {
        if ($channel === self::MAIL) {
            return Password::sendResetLink(['email' => $email]) === Password::RESET_LINK_SENT;
        }

        $user = User::query()->where('email', $email)->first();

        if ($user === null) {
            return false;
        }

        $link = $this->link($user);

        return match ($channel) {
            self::TELEGRAM => $user->telegram_chat_id !== null
                && $this->telegram->send($user->telegram_chat_id, $this->message($link)),
            self::WHATSAPP => filled($user->phone)
                && $this->whatsapp->send((string) $user->phone, $link, $user->locale ?? 'ru'),
            default => false,
        };
    }

    /** Ссылка со свежим одноразовым токеном — той же породы, что в письме. */
    private function link(User $user): string
    {
        $token = Password::broker()->createToken($user);

        return url(route('password.reset', ['token' => $token, 'email' => $user->email], false));
    }

    private function message(string $link): string
    {
        return __('ui.messages.auth.reset_message', ['link' => $link]);
    }
}
