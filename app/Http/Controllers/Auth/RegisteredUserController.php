<?php

declare(strict_types=1);

namespace App\Http\Controllers\Auth;

use App\Http\Controllers\Controller;
use App\Http\Requests\Auth\RegisterRequest;
use App\Models\Plan;
use App\Models\User;
use App\Support\Locales;
use Illuminate\Auth\Events\Registered;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\DB;
use Inertia\Inertia;
use Inertia\Response;

class RegisteredUserController extends Controller
{
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

        return Inertia::render('auth/Register');
    }

    public function store(RegisterRequest $request): RedirectResponse
    {
        // Компания создаётся на следующем шаге онбординга, здесь только человек.
        // Транзакция нужна, чтобы событие Registered не ушло при неудачной записи.
        $user = DB::transaction(function () use ($request): User {
            return User::create([
                'name' => $request->string('name')->toString(),
                'email' => $request->string('email')->toString(),
                'phone' => $request->string('phone')->toString(),
                'password' => $request->string('password')->toString(),
                'locale' => $request->string('locale', 'ru')->toString(),
                'company_role' => User::ROLE_OWNER,
            ]);
        });

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
         * Второй шаг — данные компании. Отдельным экраном, а не полями
         * в этой же форме: восемь дополнительных полей в регистрации
         * заметно снижают долю дошедших до конца. Шаг пропускаемый.
         */
        return redirect()->route('onboarding.company');
    }
}
