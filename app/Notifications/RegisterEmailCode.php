<?php

declare(strict_types=1);

namespace App\Notifications;

use Illuminate\Notifications\Messages\MailMessage;
use Illuminate\Notifications\Notification;

/**
 * Письмо с кодом на первом шаге регистрации.
 *
 * Учётной записи ещё нет — письмо уходит на адрес (Notification::route),
 * и ссылки «подтвердить одним нажатием» в нём нет: подтверждать пока
 * нечего, код вводится на втором шаге в той же вкладке.
 */
class RegisterEmailCode extends Notification
{
    public function __construct(public readonly string $code) {}

    /** @return list<string> */
    public function via(object $notifiable): array
    {
        return ['mail'];
    }

    public function toMail(object $notifiable): MailMessage
    {
        return (new MailMessage)
            ->subject("Код подтверждения {$this->code} — SAVDEX")
            ->greeting('Здравствуйте!')
            ->line('Ваш код для регистрации на площадке SAVDEX:')
            ->line("# {$this->code}")
            ->line('Введите его на странице регистрации. Код действует 15 минут и работает один раз.')
            ->line('Если вы не регистрировались на SAVDEX, просто удалите это письмо.')
            ->salutation('Команда SAVDEX');
    }
}
