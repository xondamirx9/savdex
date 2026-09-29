<?php

declare(strict_types=1);

namespace App\Http\Controllers\Auth;

use App\Http\Controllers\Controller;
use App\Http\Requests\Auth\RegisterRequest;
use App\Models\Category;
use App\Models\Company;
use App\Models\ItTask;
use App\Models\Plan;
use App\Models\User;
use App\Support\Locales;
use Illuminate\Auth\Events\Registered;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\RateLimiter;
use Inertia\Inertia;
use Inertia\Response;

class RegisteredUserController extends Controller
{
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

        return Inertia::render('auth/Register', [
            // Юрлицо выбирает, чем торгует, — разделы каталога верхнего уровня
            'categories' => Category::query()->whereNull('parent_id')->where('is_active', true)
                ->with('translations')->orderBy('sort')->orderBy('id')->get()
                ->map(fn (Category $c): array => ['id' => $c->id, 'name' => $c->name()]),
            // Фрилансер — направление «Доп. услуг», на заказы которого откликается
            'serviceSections' => ItTask::sectionTree(),
        ]);
    }

    public function store(RegisterRequest $request): RedirectResponse
    {
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
         * Демо-стенд (см. config/app.php): почта помечается подтверждённой
         * до события Registered — слушатель уведомлений видит это и письмо
         * не отправляет.
         */
        if (config('app.demo_auto_verify')) {
            $user->markEmailAsVerified();
        }

        event(new Registered($user));
        Auth::login($user);

        /*
         * Второй шаг — данные компании — только у юрлица: тип бизнеса,
         * страна, город и роль на площадке. Физлицу и фрилансеру
         * больше спрашивать нечего — сразу подтверждение почты.
         */
        if ($type === Company::LEGAL_ENTITY) {
            return redirect()->route('onboarding.company');
        }

        return redirect()->route('verification.notice')
            ->with('success', __('ui.messages.company.created_onboarding'));
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
