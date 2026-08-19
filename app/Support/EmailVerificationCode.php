<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\User;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Hash;

/**
 * Код подтверждения почты из письма.
 *
 * Код — шесть цифр, живёт ограниченное время и лежит в кэше хешем:
 * утечка кэша не раскрывает действующие коды, а по истечении срока
 * запись исчезает сама, без чистильщика.
 *
 * Попытки ввода считаются здесь же, а не только ограничением частоты
 * маршрута: перебор шестизначного кода за пять попыток невозможен,
 * и после лимита код гасится — даже угаданный на шестой раз уже не
 * сработает.
 */
class EmailVerificationCode
{
    public const TTL_MINUTES = 15;

    private const MAX_ATTEMPTS = 5;

    /** Выпустить новый код взамен прежнего и вернуть его для письма. */
    public static function issue(User $user): string
    {
        // random_int из криптографического источника; нижняя граница
        // 100000 заодно исключает коды с ведущим нулём, которые
        // человек набирает как пять цифр и получает «неверный код»
        $code = (string) random_int(100000, 999999);

        Cache::put(self::key($user), [
            'hash' => Hash::make($code),
            'attempts' => 0,
        ], now()->addMinutes(self::TTL_MINUTES));

        return $code;
    }

    /** Проверить код; верный код одноразов — запись гасится сразу. */
    public static function check(User $user, string $code): bool
    {
        $entry = Cache::get(self::key($user));

        if (! is_array($entry)) {
            return false;
        }

        if ($entry['attempts'] >= self::MAX_ATTEMPTS) {
            Cache::forget(self::key($user));

            return false;
        }

        if (! Hash::check($code, $entry['hash'])) {
            $entry['attempts']++;
            Cache::put(self::key($user), $entry, now()->addMinutes(self::TTL_MINUTES));

            return false;
        }

        Cache::forget(self::key($user));

        return true;
    }

    private static function key(User $user): string
    {
        return "email_verification_code.{$user->id}";
    }
}
