<?php

declare(strict_types=1);

namespace App\Http\Middleware;

use Closure;
use Illuminate\Http\Request;
use Symfony\Component\HttpFoundation\Response;

/**
 * Выданный вручную пароль знают двое — тот, кто выдал, и тот, кому
 * выдали. До замены доступ нельзя считать принадлежащим человеку.
 *
 * Раньше это работало только на входе: человека один раз уводило на
 * смену пароля, а дальше он просто открывал /cabinet руками и работал.
 * Временный пароль давал публикацию объявлений, правку компании и
 * выгрузку купленных контактов — то есть ровно то, ради чего аккаунт
 * и уводят. Теперь проверка стоит на всех маршрутах кабинета
 * и в панели Filament.
 */
class RequirePasswordChange
{
    /**
     * Маршруты, доступные с невозвращённым флагом.
     *
     * Сама смена пароля — иначе редирект зациклится. Выход — человек
     * должен иметь возможность просто уйти. Смена языка — экран смены
     * пароля тоже переводится.
     */
    private const ALLOWED = [
        'password.forced',
        'password.forced.update',
        'logout',
        'locale.update',
        // Ссылка из письма подписана и живёт час: увести с неё на смену
        // пароля значит сжечь её, а подтверждать почту заново человек
        // будет уже с раздражением
        'verification.*',
    ];

    public function handle(Request $request, Closure $next): Response
    {
        if (! ($request->user()?->must_change_password) || $request->routeIs(self::ALLOWED)) {
            return $next($request);
        }

        /*
         * Inertia ждёт ответ своего формата: обычный редирект на XHR
         * страница показала бы как ошибку, а не как переход.
         */
        return redirect()->route('password.forced')
            ->with('warning', 'Смените выданный пароль — до этого разделы кабинета закрыты.');
    }
}
