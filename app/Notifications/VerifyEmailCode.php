<?php

declare(strict_types=1);

namespace App\Notifications;

use Illuminate\Auth\Notifications\VerifyEmail;
use Illuminate\Notifications\Messages\MailMessage;

/**
 * Письмо подтверждения почты: код для ввода на сайте плюс прежняя
 * подписанная ссылка-кнопка.
 *
 * Код появился по требованию пользователей мобильной почты: письмо
 * открывают на телефоне, а регистрируются на компьютере — ссылка
 * подтверждает сессию не в том браузере, а код вводится там, где
 * человек регистрировался.
 *
 * Наследует штатное VerifyEmail, а не собирает письмо с нуля: ссылка
 * строится тем же verificationUrl с подписью и сроком жизни, что и
 * раньше, — маршрут verification.verify продолжает работать.
 */
class VerifyEmailCode extends VerifyEmail
{
    public function __construct(public readonly string $code) {}

    protected function buildMailMessage($url): MailMessage
    {
        return (new MailMessage)
            ->subject("Код подтверждения {$this->code} — SAVDEX")
            ->greeting('Здравствуйте!')
            ->line('Ваш код подтверждения почты на площадке SAVDEX:')
            ->line("# {$this->code}")
            ->line('Введите его на странице подтверждения. Код действует 15 минут и работает один раз.')
            ->action('Или подтвердите одним нажатием', $url)
            ->line('Если вы не регистрировались на SAVDEX, просто удалите это письмо — без подтверждения учётная запись не активируется.')
            ->salutation('Команда SAVDEX');
    }
}
