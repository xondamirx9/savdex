<?php

declare(strict_types=1);

namespace App\Support\Microsite;

/**
 * Адреса мини-сайтов: acme.savdex.site.
 *
 * Схема и порт берутся из APP_URL: на боевом сервере это https,
 * а локально — http://acme.localhost:8000 рядом с http://localhost:8000.
 */
final class SiteHost
{
    /** Формат поддомена: латиница, цифры и дефис не по краям, 3–40 знаков. */
    public const PATTERN = '/^[a-z0-9](?:[a-z0-9-]{1,38})[a-z0-9]$/';

    public static function domain(): string
    {
        return strtolower((string) config('microsite.domain'));
    }

    /** Запрос пришёл на домен мини-сайтов — на сам домен или поддомен. */
    public static function matches(string $host): bool
    {
        $host = strtolower($host);
        $domain = self::domain();

        return $domain !== '' && ($host === $domain || str_ends_with($host, '.'.$domain));
    }

    /** Поддомен из хоста; null — это не мини-сайт или сам домен без поддомена. */
    public static function subdomain(string $host): ?string
    {
        $host = strtolower($host);
        $suffix = '.'.self::domain();

        if (! str_ends_with($host, $suffix)) {
            return null;
        }

        $sub = substr($host, 0, -strlen($suffix));

        // Вложенные поддомены (a.b.savdex.site) не выдаются никому
        return $sub !== '' && ! str_contains($sub, '.') ? $sub : null;
    }

    public static function url(string $subdomain): string
    {
        $app = parse_url((string) config('app.url'));
        $scheme = $app['scheme'] ?? 'https';
        $port = isset($app['port']) ? ':'.$app['port'] : '';

        return "{$scheme}://{$subdomain}.".self::domain().$port;
    }

    public static function isReserved(string $subdomain): bool
    {
        return in_array($subdomain, (array) config('microsite.reserved'), true);
    }

    /**
     * Поддомен, который стоит предложить по умолчанию, — из адреса
     * карточки компании: он уже транслитерирован и уникален на площадке.
     */
    public static function suggest(string $slug): string
    {
        $sub = trim((string) preg_replace('/[^a-z0-9-]+/', '-', strtolower($slug)), '-');
        $sub = trim(substr((string) preg_replace('/-{2,}/', '-', $sub), 0, 40), '-');

        return strlen($sub) >= 3 ? $sub : $sub.'-site';
    }
}
