<?php

declare(strict_types=1);

namespace App\Support\Microsite;

/**
 * Адреса мини-сайтов.
 *
 * Два режима, выбор — MICROSITE_DOMAIN:
 * — не задан: страница на самой площадке, savdex.uz/s/acme;
 * — задан: свой поддомен, acme.savdex.site.
 *
 * Поле company_sites.subdomain в обоих режимах одно и то же: при
 * переходе на домен адреса компаний не меняются, меняется только вид.
 *
 * Схема и порт поддомена берутся из APP_URL: на боевом сервере это
 * https, а локально — http://acme.site.localhost:8000.
 */
final class SiteHost
{
    /** Формат поддомена: латиница, цифры и дефис не по краям, 3–40 знаков. */
    public const PATTERN = '/^[a-z0-9](?:[a-z0-9-]{1,38})[a-z0-9]$/';

    /** Префикс пути мини-сайтов на площадке: savdex.uz/s/acme. */
    public const PATH_PREFIX = 's';

    public static function domain(): string
    {
        return strtolower(trim((string) config('microsite.domain')));
    }

    /** Мини-сайты на своих поддоменах, а не страницами площадки. */
    public static function usesSubdomains(): bool
    {
        return self::domain() !== '';
    }

    /** Запрос пришёл на домен мини-сайтов — на сам домен или поддомен. */
    public static function matches(string $host): bool
    {
        if (! self::usesSubdomains()) {
            return false;
        }

        $host = strtolower($host);
        $domain = self::domain();

        return $host === $domain || str_ends_with($host, '.'.$domain);
    }

    /** Поддомен из хоста; null — это не мини-сайт или сам домен без поддомена. */
    public static function subdomain(string $host): ?string
    {
        if (! self::usesSubdomains()) {
            return null;
        }

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
        if (! self::usesSubdomains()) {
            return rtrim((string) config('app.url'), '/').'/'.self::PATH_PREFIX.'/'.$subdomain;
        }

        $app = parse_url((string) config('app.url'));
        $scheme = $app['scheme'] ?? 'https';
        $port = isset($app['port']) ? ':'.$app['port'] : '';

        return "{$scheme}://{$subdomain}.".self::domain().$port;
    }

    /**
     * Как адрес выглядит в форме редактора: что стоит до поля ввода
     * и что после. «savdex.uz/s/» + acme или acme + «.savdex.site».
     *
     * @return array{prefix: string, suffix: string}
     */
    public static function addressParts(): array
    {
        if (self::usesSubdomains()) {
            return ['prefix' => '', 'suffix' => '.'.self::domain()];
        }

        $host = (string) parse_url((string) config('app.url'), PHP_URL_HOST);

        return ['prefix' => $host.'/'.self::PATH_PREFIX.'/', 'suffix' => ''];
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
