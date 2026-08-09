<?php

declare(strict_types=1);

namespace App\Http\Middleware;

use App\Support\Locales;
use Closure;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

/**
 * Язык из адреса.
 *
 * Снимает языковой префикс до того, как сработает маршрутизация:
 * «/uz/catalog» превращается в «/catalog», а выбранный язык уезжает
 * в атрибуты запроса. Дальше всё приложение — маршруты, контроллеры,
 * route() — работает с адресами без языка и ничего о нём не знает.
 *
 * Почему так, а не пятью наборами маршрутов с префиксом: набор
 * пришлось бы регистрировать по разу на язык, имена маршрутов
 * задваивались бы, а каждый redirect()->route() в контроллерах нужно
 * было бы учить языку. Здесь всё сводится к одному месту.
 *
 * Обратный ход — на выходе: адрес, на который уводит редирект,
 * получает префикс обратно. Без этого человек, отправивший форму
 * из узбекской версии, приземлялся бы на русскую.
 */
class LocalizeUrl
{
    /** Атрибут запроса, откуда язык читает SetLocale. */
    public const ATTRIBUTE = 'url_locale';

    /**
     * Пометка «адрес перенаправления трогать не нужно».
     *
     * Ставится там, где язык выбирает сам обработчик — например при
     * переключении языка. Иначе переход с узбекского на русский
     * возвращался бы обратно на узбекский: адрес русской версии
     * префикса не имеет, и middleware добавил бы его снова.
     */
    public const KEEP = 'keep_target_locale';

    public function handle(Request $request, Closure $next): Response
    {
        [$locale, $path] = Locales::split($request->getPathInfo());

        if ($locale !== null) {
            $request->attributes->set(self::ATTRIBUTE, $locale);
            $this->rewrite($request, $path);
        }

        $response = $next($request);

        if ($locale === null || $request->attributes->get(self::KEEP) === true) {
            return $response;
        }

        return $this->localizeRedirect($response, $locale);
    }

    /**
     * Переписать адрес запроса без языкового префикса.
     *
     * initialize() нужен целиком, а не подмена REQUEST_URI: Symfony
     * разбирает адрес один раз и держит разобранное в объекте —
     * иначе маршрутизация пошла бы по старому пути.
     */
    private function rewrite(Request $request, string $path): void
    {
        $server = $request->server->all();
        $query = $request->getQueryString();

        $server['REQUEST_URI'] = $path.($query !== null ? '?'.$query : '');

        $request->initialize(
            $request->query->all(),
            $request->request->all(),
            $request->attributes->all(),
            $request->cookies->all(),
            $request->files->all(),
            $server,
            $request->getContent(),
        );
    }

    /**
     * Вернуть префикс в адрес перенаправления.
     *
     * Только для своих адресов: платёжные системы и внешние сервисы
     * к нашим языкам отношения не имеют.
     */
    private function localizeRedirect(Response $response, string $locale): Response
    {
        if (! $response instanceof RedirectResponse) {
            return $response;
        }

        $target = $response->getTargetUrl();
        $root = url('/');

        if (! str_starts_with($target, $root)) {
            return $response;
        }

        $path = substr($target, strlen($root));

        return $response->setTargetUrl(Locales::url($path === '' ? '/' : $path, $locale));
    }
}
