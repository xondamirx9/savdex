<?php

declare(strict_types=1);

namespace App\Http\Controllers\Auth;

use App\Http\Controllers\Controller;
use App\Support\EmailVerificationCode;
use Illuminate\Auth\Events\Verified;
use Illuminate\Foundation\Auth\EmailVerificationRequest;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Подтверждение почты.
 *
 * Маршрут verification.verify обязателен: письмо, которое Laravel шлёт
 * по событию Registered, строит ссылку именно через route('verification.verify').
 * Без него регистрация падала с 500 — ошибка вылезала уже после создания
 * пользователя, поэтому аккаунт создавался, а человек видел белый экран.
 */
class EmailVerificationController extends Controller
{
    public function notice(Request $request): RedirectResponse|Response
    {
        if ($request->user()->hasVerifiedEmail()) {
            return redirect()->route('cabinet');
        }

        return Inertia::render('auth/VerifyEmail', [
            'email' => $request->user()->email,
            'status' => $request->session()->get('status'),
        ]);
    }

    /** Ссылка подписана и живёт 24 часа — подделать её нельзя. */
    public function verify(EmailVerificationRequest $request): RedirectResponse
    {
        if ($request->user()->hasVerifiedEmail()) {
            return redirect()->route('cabinet')->with('success', 'Почта уже подтверждена');
        }

        $request->fulfill();

        return redirect()->route('cabinet')->with('success', 'Почта подтверждена — теперь доступна публикация объявлений');
    }

    /**
     * Подтверждение кодом из письма.
     *
     * Код нужен тем, кто читает почту не там, где регистрировался:
     * ссылка из письма открывается в браузере телефона без сессии,
     * а код вводится в уже открытой вкладке. Перебор закрыт дважды:
     * ограничением частоты на маршруте и счётчиком попыток в самом коде.
     */
    public function confirm(Request $request): RedirectResponse
    {
        if ($request->user()->hasVerifiedEmail()) {
            return redirect()->route('cabinet');
        }

        $request->validate(
            ['code' => ['required', 'digits:6']],
            ['code.required' => 'Введите код из письма', 'code.digits' => 'Код — шесть цифр'],
        );

        if (! EmailVerificationCode::check($request->user(), $request->string('code')->toString())) {
            return back()->withErrors([
                'code' => 'Код не подошёл или устарел. Отправьте письмо повторно и введите код из него.',
            ]);
        }

        if ($request->user()->markEmailAsVerified()) {
            event(new Verified($request->user()));
        }

        return redirect()->route('cabinet')->with('success', 'Почта подтверждена — теперь доступна публикация объявлений');
    }

    public function send(Request $request): RedirectResponse
    {
        if ($request->user()->hasVerifiedEmail()) {
            return redirect()->route('cabinet');
        }

        $request->user()->sendEmailVerificationNotification();

        return back()->with('status', 'Письмо отправлено повторно. Не пришло — проверьте папку «Спам».');
    }
}
