<?php

declare(strict_types=1);

namespace App\Http\Controllers\Auth;

use App\Http\Controllers\Controller;
use App\Models\User;
use App\Services\Auth\LoginThrottle;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Validation\ValidationException;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Вход в систему.
 *
 * Реализует NEG-02, NEG-03 и NEG-06d из QA.md:
 * — счётчик неудачных попыток на сервере;
 * — единое сообщение для «нет пользователя» и «неверный пароль»,
 *   иначе форма превращается в инструмент проверки, зарегистрирован ли адрес;
 * — блокировка с точным обратным отсчётом, а не «попробуйте позже».
 */
class AuthenticatedSessionController extends Controller
{
    /**
     * Форма входа.
     *
     * status пробрасывается обязательно: после смены пароля контроллер
     * сброса делает redirect()->route('login')->with('status', …), и без
     * этой строки человек возвращался на пустую форму, не понимая,
     * сохранился новый пароль или нет.
     */
    public function create(Request $request): Response
    {
        return Inertia::render('auth/Login', [
            'status' => $request->session()->get('status'),
        ]);
    }

    public function store(Request $request): RedirectResponse
    {
        $credentials = $request->validate([
            'email' => ['required', 'string', 'email'],
            'password' => ['required', 'string'],
        ], [
            'email.required' => __('ui.messages.auth.email_required'),
            'email.email' => __('ui.messages.auth.email_invalid'),
            'password.required' => __('ui.messages.auth.password_required'),
        ]);

        $email = mb_strtolower(trim($credentials['email']));
        $throttle = new LoginThrottle($email, (string) $request->ip());

        if ($throttle->isLocked()) {
            throw ValidationException::withMessages([
                'email' => $this->lockoutMessage($throttle),
            ]);
        }

        $remember = $request->boolean('remember');

        if (! Auth::attempt(['email' => $email, 'password' => $credentials['password']], $remember)) {
            $throttle->recordFailure($request->userAgent());

            // Перечитываем счётчик после записи, чтобы показать актуальный остаток
            $fresh = new LoginThrottle($email, (string) $request->ip());

            throw ValidationException::withMessages([
                'email' => $fresh->isLocked()
                    ? $this->lockoutMessage($fresh)
                    : __('ui.messages.auth.wrong_credentials', [
                        'left' => $fresh->remainingAttempts(),
                        'total' => LoginThrottle::MAX_ATTEMPTS,
                    ]),
            ]);
        }

        /** @var User $user */
        $user = Auth::user();

        // Заблокированного пользователя не пускаем даже с верным паролем
        if ($user->status !== 'active') {
            Auth::logout();
            $request->session()->invalidate();

            throw ValidationException::withMessages([
                'email' => __('ui.messages.auth.blocked'),
            ]);
        }

        $throttle->recordSuccess($request->userAgent());
        $request->session()->regenerate();

        $user->forceFill([
            'last_login_at' => now(),
            'last_login_ip' => $request->ip(),
        ])->save();

        // Пароль, выданный суперадмином вручную, обязателен к смене (NEG-06f)
        if ($user->must_change_password) {
            return redirect()->route('password.forced');
        }

        return redirect()->intended(route('cabinet'));
    }

    public function destroy(Request $request): RedirectResponse
    {
        Auth::logout();
        $request->session()->invalidate();
        $request->session()->regenerateToken();

        return redirect('/');
    }

    /** Сообщение о блокировке с человекочитаемым остатком времени. */
    private function lockoutMessage(LoginThrottle $throttle): string
    {
        $seconds = $throttle->secondsUntilUnlock();
        $minutes = (int) ceil($seconds / 60);

        return __('ui.messages.auth.locked_out', ['minutes' => max(1, $minutes)]);
    }
}
