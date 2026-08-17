<?php

use App\Http\Middleware\CanonicalHost;
use App\Http\Middleware\HandleInertiaRequests;
use App\Http\Middleware\LocalizeUrl;
use App\Http\Middleware\SetLocale;
use Illuminate\Foundation\Application;
use Illuminate\Foundation\Configuration\Exceptions;
use Illuminate\Foundation\Configuration\Middleware;
use Illuminate\Http\Middleware\AddLinkHeadersForPreloadedAssets;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

return Application::configure(basePath: dirname(__DIR__))
    ->withRouting(
        web: __DIR__.'/../routes/web.php',
        commands: __DIR__.'/../routes/console.php',
        health: '/up',
    )
    ->withMiddleware(function (Middleware $middleware): void {
        /*
         * Языковой префикс снимается до маршрутизации — иначе каждый
         * маршрут пришлось бы регистрировать по разу на язык.
         * Отсюда и глобальный стек: web-группа работает уже после
         * того, как маршрут выбран.
         */
        $middleware->prepend(LocalizeUrl::class);

        /*
         * Уводит со служебного адреса Render на свой домен. Стоит
         * впереди LocalizeUrl: тот снимает языковой префикс с пути,
         * и перенаправление, собранное после него, теряло бы язык.
         */
        $middleware->prepend(CanonicalHost::class);

        /*
         * На хостинге приложение стоит за обратным прокси (Render,
         * Cloudflare и т.п.): без доверия к X-Forwarded-* Laravel видит
         * http и внутренний хост — ссылки и куки собираются неверно.
         */
        $middleware->trustProxies(at: '*');

        $middleware->web(append: [
            SetLocale::class,
            HandleInertiaRequests::class,
            AddLinkHeadersForPreloadedAssets::class,
        ]);

        /*
         * Колбэк платёжного провайдера приходит снаружи и не несёт наш
         * CSRF-токен: провайдер о нём не знает. Подлинность колбэка
         * проверяется подписью в платёжном шлюзе, а не токеном формы.
         */
        $middleware->validateCsrfTokens(except: ['payments/*/callback', 'payments/*/callback/*']);
    })
    ->withExceptions(function (Exceptions $exceptions): void {
        $exceptions->shouldRenderJsonWhen(
            fn (Request $request) => $request->is('api/*'),
        );

        /*
         * Страницы ошибок в оформлении сайта.
         *
         * По умолчанию Laravel отдаёт служебную страницу на английском —
         * человек видит «404 | Not Found» и не понимает, что делать.
         * Показываем то же, что и на остальных страницах: объяснение
         * на русском и выход из ситуации.
         */
        $exceptions->respond(function (Response $response, Throwable $e, Request $request) {
            $status = $response->getStatusCode();

            if ($request->is('api/*')) {
                return $response;
            }

            if (! in_array($status, [403, 404, 419, 429, 500, 503], true)) {
                return $response;
            }

            // В режиме отладки подробный отчёт нужен только для ошибок сервера:
            // у 404 отлаживать нечего, а разработчик должен видеть страницу
            // ровно такой, какой её увидит пользователь
            if ($status >= 500 && app()->hasDebugModeEnabled()) {
                return $response;
            }

            /*
             * Общие пропсы кладёт HandleInertiaRequests, но он живёт
             * в web-группе, а групповые посредники не запускаются, когда
             * маршрут не совпал (404) или CSRF не сошёлся (419). Без них
             * шапка страницы ошибки рисовала ключи вместо словаря
             * («nav.companies»), а переключатель языка падал на пустом
             * списке. Поэтому минимум — язык, словарь, ссылки языков —
             * собирается здесь же.
             *
             * Язык берём из префикса адреса: LocalizeUrl глобальный
             * и успел его снять даже на несуществующем маршруте.
             */
            $fromUrl = $request->attributes->get(LocalizeUrl::ATTRIBUTE);

            if (\App\Support\Locales::supports($fromUrl)) {
                app()->setLocale($fromUrl);
            }

            return inertia('Error', [
                'status' => $status,
                // Код обращения для поддержки: по нему в логах ищется
                // конкретная ошибка, а не «что-то сломалось вчера»
                'reference' => $status >= 500 ? substr(md5((string) $e->getMessage().now()->timestamp), 0, 8) : null,
                'locale' => app()->getLocale(),
                'translations' => trans('ui'),
                'localeLinks' => array_map(fn (string $code): array => [
                    'code' => $code,
                    'label' => \App\Support\Locales::ALL[$code]['label'],
                    'short' => \App\Support\Locales::ALL[$code]['short'],
                    'url' => \App\Support\Locales::switchUrl($request->getRequestUri(), $code),
                ], \App\Support\Locales::codes()),
            ])
                ->toResponse($request)
                ->setStatusCode($status);
        });
    })->create();
