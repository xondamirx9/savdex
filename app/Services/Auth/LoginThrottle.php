<?php

declare(strict_types=1);

namespace App\Services\Auth;

use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;

/**
 * Ограничение попыток входа — реализация NEG-02 и NEG-03 из QA.md.
 *
 * Счётчик живёт в базе, а не в сессии: сессионный счётчик обходится
 * очисткой cookie, то есть не защищает вообще ни от чего.
 *
 * Считаем по связке почта + IP. Только по почте — можно заблокировать
 * чужой аккаунт, зная адрес. Только по IP — не ловит перебор из ботнета.
 */
final class LoginThrottle
{
    /** После скольких неудач блокируем. */
    public const MAX_ATTEMPTS = 5;

    /** На сколько минут блокируем. */
    public const LOCKOUT_MINUTES = 15;

    /** За какое окно считаем неудачные попытки. */
    private const WINDOW_MINUTES = 15;

    public function __construct(private readonly string $email, private readonly string $ip) {}

    /** Сколько неудачных попыток накоплено в текущем окне. */
    public function failedAttempts(): int
    {
        return DB::table('login_attempts')
            ->where('email', $this->email)
            ->where('ip', $this->ip)
            ->where('successful', false)
            ->where('created_at', '>=', now()->subMinutes(self::WINDOW_MINUTES))
            ->count();
    }

    public function remainingAttempts(): int
    {
        return max(0, self::MAX_ATTEMPTS - $this->failedAttempts());
    }

    public function isLocked(): bool
    {
        return $this->remainingAttempts() === 0;
    }

    /**
     * Когда блокировка снимется. Показываем пользователю обратный отсчёт —
     * «попробуйте позже» без срока раздражает и порождает обращения в поддержку.
     */
    public function unlocksAt(): ?Carbon
    {
        if (! $this->isLocked()) {
            return null;
        }

        $oldest = DB::table('login_attempts')
            ->where('email', $this->email)
            ->where('ip', $this->ip)
            ->where('successful', false)
            ->where('created_at', '>=', now()->subMinutes(self::WINDOW_MINUTES))
            ->orderByDesc('created_at')
            ->limit(self::MAX_ATTEMPTS)
            ->value('created_at');

        return $oldest
            ? Carbon::parse($oldest)->addMinutes(self::LOCKOUT_MINUTES)
            : now()->addMinutes(self::LOCKOUT_MINUTES);
    }

    public function secondsUntilUnlock(): int
    {
        $at = $this->unlocksAt();

        return $at ? max(0, (int) now()->diffInSeconds($at, false)) : 0;
    }

    public function recordFailure(?string $userAgent = null): void
    {
        $this->record(false, $userAgent);
    }

    /** Успешный вход обнуляет счётчик — иначе блокировка догонит позже. */
    public function recordSuccess(?string $userAgent = null): void
    {
        $this->record(true, $userAgent);

        DB::table('login_attempts')
            ->where('email', $this->email)
            ->where('ip', $this->ip)
            ->where('successful', false)
            ->delete();
    }

    private function record(bool $successful, ?string $userAgent): void
    {
        DB::table('login_attempts')->insert([
            'email' => $this->email,
            'ip' => $this->ip,
            'successful' => $successful,
            'user_agent_hash' => $userAgent ? hash('sha256', $userAgent) : null,
            'created_at' => now(),
        ]);
    }
}
