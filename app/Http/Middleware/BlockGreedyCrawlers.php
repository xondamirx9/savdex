<?php

declare(strict_types=1);

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

/**
 * Отказ коммерческим SEO-роботам.
 *
 * Площадка отдаёт каждую карточку на пяти языках: семьсот с лишним
 * компаний и объявлений превращаются в три с половиной тысячи страниц,
 * и каждая — полный рендер на ~35 КБ. Робот обходит их подряд, с
 * десятка адресов сразу.
 *
 * Пока потолок процессов Apache стоял на дебиановских ста пятидесяти,
 * этого никто не замечал: процессы просто плодились, пока не кончалась
 * память. Теперь потолок считается от памяти и невелик — и каждый
 * процесс, занятый роботом, это процесс, не занятый человеком.
 *
 * Здесь перечислены только те, кто не приносит ни одного посетителя:
 * это инструменты анализа ссылок, они обходят чужие сайты, чтобы
 * продавать собранное своим подписчикам. Поисковики — Google, Яндекс,
 * Bing, DuckDuckGo, Apple, Petal — не тронуты намеренно: они приводят
 * покупателей, ради них карта сайта и существует.
 *
 * robots.txt просит о том же, но его читают по своему расписанию и
 * не все. Здесь — отказ сразу.
 */
class BlockGreedyCrawlers
{
    /**
     * Имена роботов так, как они называют себя сами: этот же список
     * уходит в robots.txt (см. маршрут /robots.txt), поэтому он один
     * на оба места — два разошлись бы на первом же дополнении.
     *
     * @var list<string>
     */
    public const CRAWLERS = [
        'AhrefsBot',      // Ahrefs
        'SemrushBot',     // Semrush
        'MJ12bot',        // Majestic
        'DotBot',         // Moz
        'rogerbot',       // Moz
        'BLEXBot',        // WebMeUp
        'DataForSeoBot',  // DataForSEO
        'Barkrowler',     // Babbar
        'serpstatbot',    // Serpstat
        'SEOkicks',       // SEOkicks
        'ZoominfoBot',    // ZoomInfo
        'MegaIndex',      // MegaIndex
        'linkdexbot',     // Linkdex
    ];

    public function handle(Request $request, Closure $next): Response
    {
        $agent = $request->userAgent() ?? '';

        if ($agent !== '') {
            foreach (self::CRAWLERS as $crawler) {
                // stripos, а не сравнение: робот представляется строкой
                // вида «Mozilla/5.0 (compatible; AhrefsBot/7.0; …)»,
                // и регистр в ней у каждого свой.
                if (stripos($agent, $crawler) !== false) {
                    /*
                     * Простой текст, а не abort(403): обработчик ошибок
                     * рисует страницу отказа через Inertia — то есть
                     * ровно ту работу, которой мы здесь избегаем.
                     */
                    return response("Crawling is not allowed for this user agent.\n", 403, [
                        'Content-Type' => 'text/plain; charset=utf-8',
                    ]);
                }
            }
        }

        return $next($request);
    }
}
