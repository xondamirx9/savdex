<?php

declare(strict_types=1);

namespace App\Http\Controllers\Auth;

use App\Http\Controllers\Controller;
use App\Services\PasswordResetDelivery;
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
 * Ссылку можно получить не только на почту: тот, кто потерял доступ
 * к рабочему ящику, выбирает Telegram или WhatsApp — куда именно,
 * решает PasswordResetDelivery.
 *
 * Маршрут password.reset обязателен по той же причине, что и
 * verification.verify: письмо ResetPassword строит ссылку через route().
 */
class PasswordResetController extends Controller
{
    public function __construct(private readonly PasswordResetDelivery $delivery) {}

    public function request(Request $request): Response
    {
        return Inertia::render('auth/ForgotPassword', [
            'status' => $request->session()->get('status'),
            // Способы, которые площадка умеет: пока бот и WhatsApp
            // не настроены, на форме остаётся одна почта
            'channels' => $this->delivery->channels(),
        ]);
    }

    public function email(Request $request): RedirectResponse
    {
        $request->validate([
            'email' => ['required', 'email'],
            'channel' => ['nullable', 'string'],
        ]);

        $channel = $request->string('channel')->toString();

        if (! $this->delivery->supports($channel)) {
            $channel = PasswordResetDelivery::MAIL;
        }

        $this->delivery->send($request->string('email')->toString(), $channel);

        /*
         * Ответ одинаков независимо от того, есть такой адрес или нет,
         * дошло сообщение или нет. Иначе форма превращается
         * в инструмент проверки, зарегистрирован ли конкретный адрес
         * на площадке и есть ли у человека Telegram (NEG-06d из QA.md).
         */
        return back()->with('status', __('ui.messages.auth.reset_sent_'.$channel));
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
            'password.confirmed' => __('ui.messages.auth.password_mismatch'),
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
                'email' => __('ui.messages.auth.reset_expired'),
            ]);
        }

        return redirect()->route('login')->with('status', __('ui.messages.auth.password_reset'));
    }
}
