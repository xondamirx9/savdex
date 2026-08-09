<?php

declare(strict_types=1);

namespace App\Http\Middleware;

use App\Support\Locales;
use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

/**
 * Язык интерфейса.
 *
 * Порядок выбора: язык из адреса → сохранённый в профиле → сессия →
 * заголовок браузера → русский. Адрес главнее всего: ссылку могли
 * прислать в переписке, и открыть её нужно на том языке, на котором
 * её отправили, а не на том, который посетитель выбирал год назад.
 */
class SetLocale
{
    /** @deprecated Оставлено ради старого кода; источник истины — Locales. */
    public const SUPPORTED = ['ru', 'uz', 'en', 'zh', 'tr'];

    public const FALLBACK = Locales::DEFAULT;

    public function handle(Request $request, Closure $next): Response
    {
        $fromUrl = $request->attributes->get(LocalizeUrl::ATTRIBUTE);

        if (Locales::supports($fromUrl)) {
            app()->setLocale($fromUrl);

            // Выбор запоминаем: человек, пришедший по узбекской ссылке,
            // дальше ходит по площадке на узбекском
            $request->session()->put('locale', $fromUrl);

            // И в профиле — чтобы язык пережил вход с другого устройства.
            // Сравнение обязательно: иначе на каждой странице уходил бы
            // лишний UPDATE
            $user = $request->user();
            if ($user && $user->locale !== $fromUrl) {
                $user->update(['locale' => $fromUrl]);
            }

            return $next($request);
        }

        $stored = $this->stored($request);

        app()->setLocale($stored ?? Locales::DEFAULT);

        /*
         * Адрес без префикса, а язык не русский — уводим на адрес
         * этого языка. Один язык — один адрес: иначе поисковик видит
         * два разных содержимого по одному адресу, а человек не может
         * переслать ссылку, не объясняя, что «у меня открывалось иначе».
         *
         * Робот сюда не попадает: у него нет ни профиля, ни сессии,
         * и он остаётся на русской версии.
         */
        if ($stored !== null && $stored !== Locales::DEFAULT && $request->isMethod('GET') && ! $request->expectsJson() && $this->translatable($request)) {
            return redirect(Locales::url($request->getRequestUri(), $stored), 302);
        }

        return $next($request);
    }

    /**
     * Страницы, у которых язык вообще есть.
     *
     * Карта сайта, robots и выгрузка файлов одинаковы на всех языках,
     * а админка ведётся только на русском — уводить туда с префиксом
     * значит гонять лишний редирект без единого изменения на экране.
     */
    private function translatable(Request $request): bool
    {
        return ! $request->is('admin', 'admin/*', 'livewire/*', 'sitemap*.xml', 'robots.txt', 'files/*', 'up', 'storage/*');
    }

    /**
     * Язык, который человек выбирал сам.
     *
     * Заголовок браузера сюда намеренно не входит. По нему нельзя
     * перенаправлять: Googlebot ходит с «Accept-Language: en», и,
     * получив редирект, проиндексировал бы английскую версию под
     * адресом без префикса — то есть русская выдача пропала бы.
     * Заголовок используется мягче — см. suggest().
     */
    private function stored(Request $request): ?string
    {
        $user = $request->user();

        if ($user && Locales::supports($user->locale)) {
            return $user->locale;
        }

        $session = $request->session()->get('locale');

        return is_string($session) && Locales::supports($session) ? $session : null;
    }

    /**
     * Язык, который стоит предложить.
     *
     * Возвращается на страницу, чтобы показать одну строку с
     * предложением открыть её на своём языке. Предложение, а не
     * перенос: посетитель мог прийти по ссылке от партнёра именно
     * на этой версии, и уводить его с неё нельзя.
     */
    public static function suggest(Request $request): ?string
    {
        $chosen = $request->session()->has('locale') || Locales::supports($request->user()?->locale);

        // Выбор уже сделан — предлагать нечего
        if ($chosen) {
            return null;
        }

        $browser = $request->getPreferredLanguage(Locales::codes());

        return Locales::supports($browser) && $browser !== app()->getLocale() ? $browser : null;
    }
}
