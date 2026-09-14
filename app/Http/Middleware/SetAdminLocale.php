<?php

declare(strict_types=1);

namespace App\Http\Middleware;

use App\Support\Locales;
use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

/**
 * Язык админки — основной язык площадки.
 *
 * У витрины язык берётся из адреса (SetLocale), а у админки префикса
 * нет, и она работала на том языке, что стоял в APP_LOCALE. На
 * сервере переменная не задана, Laravel подставлял «en» — и посреди
 * русских подписей появлялись «Select an option» и «Construction
 * materials → Cement and concrete»: названия категорий и стран
 * берутся из переводов по текущему языку.
 *
 * Язык закреплён, а не взят из настроек окружения: подписи разделов,
 * кнопок и подсказок в админке написаны по-русски прямо в коде, и
 * справочники должны совпадать с ними, а не с APP_LOCALE.
 */
class SetAdminLocale
{
    public function handle(Request $request, Closure $next): Response
    {
        app()->setLocale(Locales::DEFAULT);

        return $next($request);
    }
}
