<?php

declare(strict_types=1);

namespace App\Http\Controllers\Auth;

use App\Http\Controllers\Controller;
use App\Models\User;
use App\Services\Auth\LoginThrottle;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Hash;
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

        if (! Auth::attempt(['email' => $email, 'password' => $credentials['password']], $remember)
            && ! $this->attemptForgiving($email, $credentials['password'], $remember)) {
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

    /**
     * Вход, который прощает искажения клавиатуры телефона.
     *
     * Если пароль при регистрации набирали в показанном виде, клавиатура
     * телефона сама делала первую букву заглавной и дописывала пробел
     * после подсказки — сохранялся не тот пароль, что человек набирал,
     * и вход с тем же паролем, набранным скрытно, отвечал «неверный
     * пароль». Поле пароля эти правки больше не допускает, а для уже
     * сохранённых проверяются те же искажения: первая буква в другом
     * регистре и пробел в конце. Так поступают и крупные сервисы
     * (Facebook принимает пароль с перевёрнутой первой буквой):
     * вариантов всего несколько, а число попыток по-прежнему ограничено.
     *
     * Почта ищется без учёта регистра: адрес, заведённый через админку
     * с заглавной буквой, иначе не находился вовсе.
     *
     * Подошёл вариант — пароль пересохраняется в том виде, в каком его
     * набрали сейчас: дальше вход проходит напрямую.
     */
    private function attemptForgiving(string $email, string $password, bool $remember): bool
    {
        $user = User::query()->whereRaw('lower(email) = ?', [$email])->first();

        if ($user === null || blank($user->password)) {
            return false;
        }

        foreach (self::keyboardVariants($password) as $variant) {
            if (Hash::check($variant, $user->password)) {
                if ($variant !== $password) {
                    $user->forceFill(['password' => $password])->save();
                }

                Auth::login($user, $remember);

                return true;
            }
        }

        return false;
    }

    /**
     * Искажения, которые вносит клавиатура телефона: первая буква другого
     * регистра, пробел в конце и то и другое вместе. Сам введённый пароль
     * тоже в списке — на случай, если не нашлась только почта.
     *
     * @return list<string>
     */
    private static function keyboardVariants(string $password): array
    {
        $first = mb_substr($password, 0, 1);
        $rest = mb_substr($password, 1);
        $flipped = mb_strtoupper($first) !== $first ? mb_strtoupper($first) : mb_strtolower($first);

        $cases = array_unique([$password, $flipped.$rest]);
        $variants = [];

        foreach ($cases as $case) {
            $variants[] = $case;
            $variants[] = $case.' ';
            $variants[] = rtrim($case);
        }

        return array_values(array_unique(array_filter($variants, fn (string $v): bool => $v !== '')));
    }

    /** Сообщение о блокировке с человекочитаемым остатком времени. */
    private function lockoutMessage(LoginThrottle $throttle): string
    {
        $seconds = $throttle->secondsUntilUnlock();
        $minutes = (int) ceil($seconds / 60);

        return __('ui.messages.auth.locked_out', ['minutes' => max(1, $minutes)]);
    }
}
