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

    public function update(Request $request): RedirectResponse
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

        // Администратора возвращаем в панель: у него может не быть
        // компании, и кабинет встретил бы его предложением её завести
        if ($user->is_admin) {
            return redirect('/admin')->with('success', 'Пароль изменён');
        }

        return redirect()->route('cabinet')->with('success', 'Пароль изменён');
    }
}
