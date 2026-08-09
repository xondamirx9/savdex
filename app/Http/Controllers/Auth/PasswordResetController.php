<?php

declare(strict_types=1);

namespace App\Http\Controllers\Auth;

use App\Http\Controllers\Controller;
use Illuminate\Auth\Events\PasswordReset;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Password;
use Illuminate\Support\Str;
use Illuminate\Validation\Rules\Password as PasswordRule;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Восстановление пароля.
 *
 * Маршрут password.reset обязателен по той же причине, что и
 * verification.verify: письмо ResetPassword строит ссылку через route().
 */
class PasswordResetController extends Controller
{
    public function request(Request $request): Response
    {
        return Inertia::render('auth/ForgotPassword', [
            'status' => $request->session()->get('status'),
        ]);
    }

    public function email(Request $request): RedirectResponse
    {
        $request->validate(['email' => ['required', 'email']]);

        Password::sendResetLink($request->only('email'));

        /*
         * Ответ одинаков независимо от того, есть такой адрес или нет.
         * Иначе форма превращается в инструмент проверки, зарегистрирован
         * ли конкретный адрес на площадке (NEG-06d из QA.md).
         */
        return back()->with('status', 'Если такой адрес зарегистрирован, письмо со ссылкой уже отправлено.');
    }

    public function reset(Request $request, string $token): Response
    {
        return Inertia::render('auth/ResetPassword', [
            'token' => $token,
            'email' => $request->string('email')->toString(),
        ]);
    }

    public function update(Request $request): RedirectResponse
    {
        $request->validate([
            'token' => ['required'],
            'email' => ['required', 'email'],
            'password' => ['required', 'confirmed', PasswordRule::defaults()],
        ], [
            'password.confirmed' => 'Пароли не совпадают',
        ]);

        $status = Password::reset(
            $request->only('email', 'password', 'password_confirmation', 'token'),
            function ($user) use ($request): void {
                $user->forceFill([
                    'password' => $request->string('password')->toString(),
                    'remember_token' => Str::random(60),
                    // Пароль сменён самим человеком — принуждать к смене больше незачем
                    'must_change_password' => false,
                ])->save();

                event(new PasswordReset($user));
            },
        );

        if ($status !== Password::PASSWORD_RESET) {
            return back()->withErrors([
                'email' => 'Ссылка недействительна или устарела. Запросите новую — они живут 60 минут.',
            ]);
        }

        return redirect()->route('login')->with('status', 'Пароль изменён. Войдите с новым паролем.');
    }
}
