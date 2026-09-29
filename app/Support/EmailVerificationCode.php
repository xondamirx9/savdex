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
        return self::issueFor(self::key($user));
    }

    /** Проверить код; верный код одноразов — запись гасится сразу. */
    public static function check(User $user, string $code): bool
    {
        return self::checkFor(self::key($user), $code);
    }

    /**
     * Код для адреса, у которого ещё нет учётной записи, — первый шаг
     * регистрации: почта подтверждается до того, как заведён аккаунт.
     */
    public static function issueForEmail(string $email): string
    {
        return self::issueFor(self::emailKey($email));
    }

    public static function checkForEmail(string $email, string $code): bool
    {
        return self::checkFor(self::emailKey($email), $code);
    }

    private static function issueFor(string $key): string
    {
        // random_int из криптографического источника; нижняя граница
        // 100000 заодно исключает коды с ведущим нулём, которые
        // человек набирает как пять цифр и получает «неверный код»
        $code = (string) random_int(100000, 999999);

        Cache::put($key, [
            'hash' => Hash::make($code),
            'attempts' => 0,
        ], now()->addMinutes(self::TTL_MINUTES));

        return $code;
    }

    private static function checkFor(string $key, string $code): bool
    {
        $entry = Cache::get($key);

        if (! is_array($entry)) {
            return false;
        }

        if ($entry['attempts'] >= self::MAX_ATTEMPTS) {
            Cache::forget($key);

            return false;
        }

        if (! Hash::check($code, $entry['hash'])) {
            $entry['attempts']++;
            Cache::put($key, $entry, now()->addMinutes(self::TTL_MINUTES));

            return false;
        }

        Cache::forget($key);

        return true;
    }

    private static function key(User $user): string
    {
        return "email_verification_code.{$user->id}";
    }

    /** Адрес — хешем: в имени файла кэша почта не нужна. */
    private static function emailKey(string $email): string
    {
        return 'register_email_code.'.sha1(mb_strtolower(trim($email)));
    }
}
