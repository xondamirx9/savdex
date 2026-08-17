<?php

declare(strict_types=1);

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

/**
 * Переезд со служебного адреса хостинга на свой домен.
 *
 * Render продолжает отдавать сайт по адресу вида savdex.onrender.com
 * и после привязки домена — отключить это нельзя. А два живых адреса
 * с одним содержимым расходятся дорого: поисковик выбирает главный сам
 * и нередко выбирает служебный, ссылки в переписке гуляют вперемешку,
 * а куки сессии, выданные на одном хосте, на другом не работают.
 *
 * Поэтому запрос на *.onrender.com уезжает на APP_URL постоянным
 * перенаправлением: 301 поисковик переносит на новый адрес вместе
 * с накопленным весом, 302 — нет.
 *
 * Своего домена в коде нет: он берётся из APP_URL. Пока переменная
 * не задана, entrypoint подставляет в неё адрес Render — хост
 * совпадает с запрошенным, и перенаправлять некуда.
 */
class CanonicalHost
{
    /** Служебный адрес хостинга, с которого уводим. */
    private const HOSTING_SUFFIX = '.onrender.com';

    /**
     * Проверка живости. Render дёргает её по своему адресу и ждёт 200:
     * перенаправление он засчитал бы как «сервис не отвечает» и снял бы
     * его с обслуживания.
     */
    private const SKIP = ['up'];

    public function handle(Request $request, Closure $next): Response
    {
        $target = $this->target($request);

        if ($target === null) {
            return $next($request);
        }

        return redirect()->away($target, 301);
    }

    /** Адрес назначения или null, если перенаправлять не нужно. */
    private function target(Request $request): ?string
    {
        /*
         * Только переходы по ссылке. На POST перенаправление опасно:
         * по 301 клиент повторяет запрос без тела и методом GET —
         * колбэк платёжного провайдера, пришедший на старый адрес,
         * так молча потерялся бы.
         */
        if (! $request->isMethodSafe()) {
            return null;
        }

        if ($request->is(...self::SKIP)) {
            return null;
        }

        $host = $request->getHost();

        if (! str_ends_with($host, self::HOSTING_SUFFIX)) {
            return null;
        }

        $canonical = rtrim((string) config('app.url'), '/');

        if ($canonical === '' || parse_url($canonical, PHP_URL_HOST) === $host) {
            return null;
        }

        // Адрес переносится целиком: языковой префикс, путь и параметры
        // запроса. Перенаправление на главную теряло бы страницу,
        // за которой человек пришёл по ссылке
        return $canonical.$request->getRequestUri();
    }
}
