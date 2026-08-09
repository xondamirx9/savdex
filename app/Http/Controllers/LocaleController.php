<?php

declare(strict_types=1);

namespace App\Http\Controllers;

use App\Http\Middleware\LocalizeUrl;
use App\Support\Locales;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;

class LocaleController extends Controller
{
    /**
     * Переключение языка.
     *
     * Основной путь другой: в переключателе стоят обычные ссылки на
     * ту же страницу с нужным префиксом — их видит поисковик и может
     * скопировать человек. Этот маршрут остался для случаев, когда
     * адреса страницы под рукой нет: переключатель на экране ошибки
     * или переход из письма.
     *
     * Возвращаем на ту же страницу, но на другом языке: уводить
     * человека на главную после смены языка — потеря контекста.
     */
    public function update(Request $request, string $locale): RedirectResponse
    {
        abort_unless(Locales::supports($locale), 404);

        // Язык в адресе ответа выбран здесь и окончательно —
        // LocalizeUrl не должен возвращать префикс страницы,
        // с которой человек уходит
        $request->attributes->set(LocalizeUrl::KEEP, true);

        $request->session()->put('locale', $locale);

        if ($user = $request->user()) {
            $user->update(['locale' => $locale]);
        }

        $referer = $request->headers->get('referer');
        $root = url('/');

        $path = is_string($referer) && str_starts_with($referer, $root)
            ? substr($referer, strlen($root))
            : '/';

        return redirect(Locales::url($path === '' ? '/' : $path, $locale));
    }
}
