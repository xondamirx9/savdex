<?php

declare(strict_types=1);

namespace App\Support;

/**
 * Подписи к правилам пароля (Password::defaults в AppServiceProvider).
 *
 * Словаря validation.php у площадки нет, и без своих подписей правило
 * отдаёт на экран ключ: на форме нового пароля по ссылке из письма и на
 * смене выданного пароля человек видел «validation.min.string» и
 * «validation.password.uncompromised» вместо объяснения. Подписи общие
 * для всех форм, где заводят пароль, — регистрации в том числе.
 */
final class PasswordMessages
{
    /**
     * @return array<string, string>
     */
    public static function all(): array
    {
        return [
            'password.min' => __('ui.messages.register.password_min'),
            'password.max' => __('ui.messages.register.password_max'),
            'password.letters' => __('ui.messages.register.password_letters'),
            'password.numbers' => __('ui.messages.register.password_numbers'),
            'password.uncompromised' => __('ui.messages.register.password_leaked'),
        ];
    }
}
