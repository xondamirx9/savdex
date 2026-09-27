<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\User;
use Illuminate\Support\Str;

/**
 * Пропуск из админки Laravel в разделы админки на Django.
 *
 * Перенос на Django идёт по частям (docs/migration-to-python.md, этап 2),
 * и первые разделы админки переезжают раньше, чем Django научится читать
 * сессию Laravel (это этап 3). Поэтому вход — через Laravel: сотрудник
 * уже вошёл в админку, Laravel выдаёт Django пропуск, а Django по нему
 * заводит свой вход.
 *
 * Пропуск — номер пользователя, адрес, куда вести, и срок в минуту,
 * подписанные HMAC-SHA256 ключом, выведенным из APP_KEY. Сам по себе
 * пропуск прав не даёт: Django по номеру заново читает пользователя
 * из базы и решает сам — роль, блокировка, смена пароля (см.
 * python/savdex/bridge.py). Передаётся POST-запросом, а не в адресе:
 * адреса оседают в журналах и истории браузера.
 *
 * Та же схема в Python — python/savdex/bridge.py; совпадение подписи
 * проверяет python/tests/test_bridge_parity.py.
 */
final class PythonBridge
{
    /** Сколько секунд пропуск действителен: ровно на переход. */
    public const TTL = 60;

    /** Куда ведёт пропуск, если адрес не указан или не годится. */
    public const HOME = '/py/admin/';

    /** Адрес Django, который принимает пропуск. */
    public const LOGIN = '/py/login';

    /**
     * Ключ подписи — из APP_KEY, но не сам APP_KEY.
     *
     * APP_KEY шифрует куки Laravel; отдавать его алгоритму, который
     * подписывает совсем другое, — лишний риск. Выведенный ключ годится
     * только для пропусков.
     */
    public static function key(): string
    {
        $key = (string) config('app.key');

        if (str_starts_with($key, 'base64:')) {
            $key = (string) base64_decode(substr($key, 7), true);
        }

        return hash_hmac('sha256', 'savdex-django-bridge-v1', $key, true);
    }

    /** Подписанный пропуск для пользователя. */
    public static function token(User $user, string $next, ?int $now = null): string
    {
        $payload = self::encode((string) json_encode([
            'uid' => $user->getKey(),
            'next' => self::safeNext($next),
            'exp' => ($now ?? time()) + self::TTL,
            'nonce' => Str::random(16),
        ], JSON_UNESCAPED_SLASHES));

        return $payload.'.'.self::encode(hash_hmac('sha256', $payload, self::key(), true));
    }

    /**
     * Только адреса Django-админки.
     *
     * Адрес приходит из запроса; без проверки пропуск стал бы
     * переадресацией куда угодно — любимый приём фишинга.
     */
    public static function safeNext(?string $next): string
    {
        $next = (string) $next;

        if (! str_starts_with($next, self::HOME) || str_contains($next, '//') || str_contains($next, '\\')
            || preg_match('/[\x00-\x1F\x7F]/', $next) === 1) {
            return self::HOME;
        }

        return $next;
    }

    private static function encode(string $bytes): string
    {
        return rtrim(strtr(base64_encode($bytes), '+/', '-_'), '=');
    }
}
