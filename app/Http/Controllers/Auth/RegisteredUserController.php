<?php

declare(strict_types=1);

namespace App\Http\Controllers\Auth;

use App\Http\Controllers\Controller;
use App\Http\Requests\Auth\RegisterEmailRequest;
use App\Http\Requests\Auth\RegisterRequest;
use App\Models\Category;
use App\Models\Company;
use App\Models\ItTask;
use App\Models\Plan;
use App\Models\User;
use App\Notifications\RegisterEmailCode;
use App\Support\EmailVerificationCode;
use App\Support\Locales;
use Illuminate\Auth\Events\Registered;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Notification;
use Illuminate\Support\Facades\RateLimiter;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Регистрация в три шага.
 *
 * 1. Почта (/register) — адрес проверяется и на него уходит код.
 * 2. Код (/register/code) — шесть цифр из письма.
 * 3. Анкета (/register/details) — кто вы, компания, телефон, пароль.
 *
 * Аккаунт заводится только на третьем шаге и сразу с подтверждённой
 * почтой: раньше почту подтверждали уже после входа, и часть людей
 * так и оставалась с неподтверждённым адресом. Между шагами адрес
 * живёт в сессии: SESSION_EMAIL — ждёт кода, SESSION_VERIFIED —
 * код введён верно.
 */
class RegisteredUserController extends Controller
{
    public const SESSION_EMAIL = 'register.email';

    public const SESSION_VERIFIED = 'register.verified_email';

    /**
     * Сколько аккаунтов можно завести с одного адреса сети за час.
     *
     * Считаются только созданные аккаунты, а не отправки формы. Раньше
     * лимит висел на маршруте (throttle:5,60) и съедался ошибками ввода:
     * короткий пароль, пароль из утечки, опечатка в телефоне — пять
     * поправок, и шестая, уже верная, отклонялась на час. Фейковые
     * компании пачками заводят успешными регистрациями, а не ошибками.
     */
    public const MAX_PER_HOUR = 5;

    public function create(Request $request): Response
    {
        /*
         * Пришёл со страницы тарифов кнопкой «Выбрать»: после регистрации
         * и подтверждения почты он должен попасть на оплату этого тарифа,
         * а не в пустой кабинет, где тариф придётся искать заново.
         * Код проверяется по справочнику — в адрес перехода попадает
         * только существующий платный тариф.
         */
        $plan = $request->string('plan')->toString();

        if ($plan !== '' && $plan !== Plan::FREE && Plan::query()->where('code', $plan)->where('is_active', true)->exists()) {
            redirect()->setIntendedUrl(Locales::url('/cabinet/billing?plan='.$plan));
        }

        return Inertia::render('auth/RegisterEmail', [
            // «Изменить почту» со второго шага — адрес уже в поле
            'email' => $request->session()->get(self::SESSION_EMAIL),
        ]);
    }

    /** Шаг 1 → 2: адрес свободен — выпустить код и отправить письмо. */
    public function sendCode(RegisterEmailRequest $request): RedirectResponse
    {
        $email = $request->string('email')->toString();

        $request->session()->put(self::SESSION_EMAIL, $email);
        $request->session()->forget(self::SESSION_VERIFIED);

        $this->mailCode($email);

        return redirect()->route('register.code');
    }

    /** Шаг 2: ввод кода. Без адреса из первого шага — назад на него. */
    public function code(Request $request): RedirectResponse|Response
    {
        $email = $request->session()->get(self::SESSION_EMAIL);

        if (! is_string($email) || $email === '') {
            return redirect()->route('register');
        }

        return Inertia::render('auth/RegisterCode', [
            'email' => $email,
            'status' => $request->session()->get('status'),
            // Только на демо-стенде без почты (mailCode)
            'demoCode' => $request->session()->get('demo_code'),
        ]);
    }

    public function confirmCode(Request $request): RedirectResponse
    {
        $email = $request->session()->get(self::SESSION_EMAIL);

        if (! is_string($email) || $email === '') {
            return redirect()->route('register');
        }

        $request->validate(
            ['code' => ['required', 'digits:6']],
            ['code.required' => __('ui.messages.auth.code_required'), 'code.digits' => __('ui.messages.auth.code_digits')],
        );

        if (! EmailVerificationCode::checkForEmail($email, $request->string('code')->toString())) {
            return back()->withErrors(['code' => __('ui.messages.auth.code_invalid')]);
        }

        $request->session()->put(self::SESSION_VERIFIED, $email);

        return redirect()->route('register.details');
    }

    /** «Отправить код ещё раз» — новый код взамен прежнего. */
    public function resendCode(Request $request): RedirectResponse
    {
        $email = $request->session()->get(self::SESSION_EMAIL);

        if (! is_string($email) || $email === '') {
            return redirect()->route('register');
        }

        $this->mailCode($email);

        return back()->with('status', __('ui.messages.auth.mail_resent'));
    }

    /** Шаг 3: анкета. Только после верного кода. */
    public function details(Request $request): RedirectResponse|Response
    {
        $email = $this->verifiedEmail($request);

        if ($email === null) {
            return redirect()->route($request->session()->has(self::SESSION_EMAIL) ? 'register.code' : 'register');
        }

        return Inertia::render('auth/Register', [
            'email' => $email,
            // Юрлицо выбирает, чем торгует, — разделы каталога верхнего уровня
            'categories' => Category::query()->whereNull('parent_id')->where('is_active', true)
                ->with('translations')->orderBy('sort')->orderBy('id')->get()
                ->map(fn (Category $c): array => ['id' => $c->id, 'name' => $c->name()]),
            // Фрилансер — направление «Доп. услуг», на заказы которого откликается
            'serviceSections' => ItTask::sectionTree(),
        ]);
    }

    public function store(Request $plain): RedirectResponse
    {
        // Без подтверждённой почты анкету не принять — к первому шагу
        if ($this->verifiedEmail($plain) === null) {
            return redirect()->route('register');
        }

        // Проверка анкеты — при разрешении запроса из контейнера
        $request = app(RegisterRequest::class);

        $limit = 'register:'.$request->ip();

        if (RateLimiter::tooManyAttempts($limit, self::MAX_PER_HOUR)) {
            // Назад с сообщением, а не 429: набранное в форме остаётся на месте
            return back()->with('error', __('ui.messages.register.too_many', [
                'minutes' => max(1, (int) ceil(RateLimiter::availableIn($limit) / 60)),
            ]));
        }

        $type = $request->accountType();

        /*
         * Профиль на площадке заводится сразу вместе с человеком: у физлица
         * и фрилансера второго шага нет, а юрлицо на втором шаге только
         * дополняет компанию типом, городом и ролью. Транзакция — чтобы
         * при сбое не остался человек без профиля и не ушло событие Registered.
         */
        $user = DB::transaction(function () use ($request, $type): User {
            $company = Company::create($this->companyData($request, $type));

            if ($type === Company::LEGAL_ENTITY) {
                $company->categories()->sync($request->input('categories', []));
            }

            return User::create([
                'name' => $request->string('name')->toString(),
                'email' => $request->string('email')->toString(),
                'phone' => $request->string('phone')->toString(),
                'password' => $request->string('password')->toString(),
                'locale' => $request->string('locale', 'ru')->toString(),
                'account_type' => $type,
                'company_id' => $company->id,
                'company_role' => User::ROLE_OWNER,
            ]);
        });

        RateLimiter::hit($limit, 3600);

        /*
         * Почта подтверждена кодом ещё до анкеты. Помечается до события
         * Registered — слушатель видит это и второе письмо не отправляет.
         */
        $user->markEmailAsVerified();
        $request->session()->forget([self::SESSION_EMAIL, self::SESSION_VERIFIED]);

        event(new Registered($user));
        Auth::login($user);

        /*
         * Второй шаг — данные компании — только у юрлица: тип бизнеса,
         * страна, город и роль на площадке. Физлицу и фрилансеру
         * больше спрашивать нечего — сразу туда, куда шли (например,
         * на оплату тарифа), иначе в кабинет.
         */
        if ($type === Company::LEGAL_ENTITY) {
            return redirect()->route('onboarding.company');
        }

        return redirect()->intended(route('cabinet'))
            ->with('success', __('ui.messages.company.created_onboarding'));
    }

    /** Адрес, подтверждённый кодом, — если он всё ещё совпадает с введённым. */
    private function verifiedEmail(Request $request): ?string
    {
        $verified = $request->session()->get(self::SESSION_VERIFIED);

        return is_string($verified) && $verified !== '' && $verified === $request->session()->get(self::SESSION_EMAIL)
            ? $verified
            : null;
    }

    private function mailCode(string $email): void
    {
        $code = EmailVerificationCode::issueForEmail($email);

        /*
         * Демо-стенд без почты (config/app.php): код в письмо не уходит,
         * а подставляется на втором шаге — иначе туда не пройти.
         */
        if (config('app.demo_auto_verify')) {
            session()->flash('demo_code', $code);

            return;
        }

        try {
            Notification::routes(['mail' => $email])->notify(new RegisterEmailCode($code));
        } catch (\Throwable $e) {
            // Сбой почты — не 500: «Отправить ещё раз» остаётся под рукой
            report($e);
        }
    }

    /**
     * Поля профиля из формы регистрации.
     *
     * @return array<string, mixed>
     */
    private function companyData(RegisterRequest $request, string $type): array
    {
        $base = [
            'legal_form' => $type,
            'status' => Company::STATUS_ACTIVE,
            'primary_role' => 'both',
        ];

        if ($type === Company::LEGAL_ENTITY) {
            return $base + [
                'name' => $request->string('company_name')->toString(),
                'tin' => $request->input('tin'),
            ];
        }

        $base += [
            // Человек выступает от своего имени — профиль называется по Ф.И.О.
            'name' => $request->string('name')->toString(),
            'tin' => $request->input('pinfl'),
        ];

        if ($type === Company::LEGAL_FREELANCER) {
            // Фрилансер сразу исполнитель: может откликаться на заказы
            // своего направления без отдельного включения роли в профиле
            $base += [
                'primary_role' => 'supplier',
                'is_it_provider' => true,
                'it_specializations' => ItTask::typesUnder($request->string('service_section')->toString()),
            ];
        }

        return $base;
    }
}
