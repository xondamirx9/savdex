<?php

declare(strict_types=1);

namespace App\Filament\Pages\Auth;

use Filament\Auth\Pages\Login as BaseLogin;
use SensitiveParameter;

/**
 * Вход в админку — почта без учёта регистра, как на сайте.
 *
 * Почта хранится строчными (регистрация и savdex:admin приводят её
 * к нижнему регистру), а стандартная форма Filament ищет её как
 * введено. PostgreSQL регистр различает, и «Savdexuz@gmail.com» —
 * телефон сам ставит заглавную первую букву — давал «неверная почта
 * или пароль», хотя на сайт с тем же вводом пускало
 * (AuthenticatedSessionController).
 */
class Login extends BaseLogin
{
    protected function getCredentialsFromFormData(#[SensitiveParameter] array $data): array
    {
        return [
            'email' => mb_strtolower(trim((string) $data['email'])),
            'password' => $data['password'],
        ];
    }
}
