<?php

declare(strict_types=1);

namespace App\Http\Middleware;

use App\Support\Microsite\SiteHost;
use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

/**
 * На домене мини-сайтов открыт только сам мини-сайт.
 *
 * Маршруты площадки не привязаны к домену и отвечали бы на любом
 * хосте: acme.savdex.site/cabinet показывал бы вход в кабинет SAVDEX
 * на адресе компании, а /catalog — весь каталог под её вывеской.
 * Поэтому здесь белый список путей, а не перечень запретов: новый
 * маршрут площадки на домен мини-сайтов сам не попадёт.
 *
 * Стоит после LocalizeUrl: языковой префикс уже снят, и /uz/
 * проверяется как /.
 */
class RestrictSiteHost
{
    private const ALLOWED = [
        '/',
        'robots.txt',
        'up',
        // Документы и фотографии компании на её сайте
        'files/*',
    ];

    public function handle(Request $request, Closure $next): Response
    {
        if (SiteHost::matches($request->getHost()) && ! $request->is(...self::ALLOWED)) {
            abort(404);
        }

        return $next($request);
    }
}
