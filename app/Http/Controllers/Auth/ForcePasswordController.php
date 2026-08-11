<?php

declare(strict_types=1);

namespace App\Http\Controllers\Auth;

use App\Http\Controllers\Controller;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Hash;
use Illuminate\Validation\Rules\Password as PasswordRule;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Принудительная смена пароля.
 *
 * Доступы создаёт суперадмин вручную (§6.3 ТЗ), поэтому первый пароль
 * известен как минимум двоим. Пока он не заменён, пользоваться площадкой
 * нельзя: флаг must_change_password снимается только здесь.
 */
class ForcePasswordController extends Controller
{
    public function edit(Request $request): RedirectResponse|Response
    {
        // Заходить сюда без флага незачем — иначе экран выглядит как ошибка
        if (! $request->user()->must_change_password) {
            return redirect()->route('cabinet');
        }

        return Inertia::render('auth/ForcePassword');
    }

    public function update(Request $request): RedirectResponse|\Symfony\Component\HttpFoundation\Response
    {
        $request->validate([
            'password' => ['required', 'string', 'confirmed', PasswordRule::defaults()],
        ], [
            'password.required' => 'Придумайте пароль',
            'password.confirmed' => 'Пароли не совпадают',
        ]);

        $user = $request->user();

        /*
         * Новый пароль не должен совпадать с выданным: иначе смена
         * формальна и доступ по-прежнему знают двое.
         */
        if (Hash::check($request->string('password')->toString(), $user->password)) {
            return back()->withErrors([
                'password' => 'Новый пароль совпадает с прежним. Придумайте другой',
            ]);
        }

        $user->forceFill([
            'password' => $request->string('password')->toString(),
            'must_change_password' => false,
        ])->save();

        /*
         * Панель хранит в сессии хеш пароля (AuthenticateSession):
         * без обновления первый же переход в /admin сверил бы сессию
         * со свежим хешем, разлогинил — и человек ходил бы по кругу
         * «вход → смена пароля → снова вход».
         */
        $request->session()->put(
            'password_hash_'.config('auth.defaults.guard'),
            $user->getAuthPassword(),
        );

        /*
         * Администратора возвращаем в панель: у него может не быть
         * компании, и кабинет встретил бы его предложением её завести.
         *
         * Именно Inertia::location, а не redirect: панель — не
         * Inertia-страница, и обычный редирект из Inertia-формы
         * привозил бы её HTML в отладочную панель поверх экрана
         * смены пароля вместо настоящего перехода.
         */
        if ($user->is_admin) {
            return Inertia::location('/admin');
        }

        return redirect()->route('cabinet')->with('success', 'Пароль изменён');
    }
}
