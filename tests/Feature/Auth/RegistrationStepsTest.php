<?php

declare(strict_types=1);

namespace Tests\Feature\Auth;

use App\Models\User;
use App\Notifications\RegisterEmailCode;
use App\Notifications\VerifyEmailCode;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Notifications\AnonymousNotifiable;
use Illuminate\Support\Facades\Notification;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\Support\LegalRegistration;
use Tests\TestCase;

/**
 * Регистрация в три шага: почта → код из письма → анкета.
 *
 * Раньше аккаунт заводился сразу, а почту подтверждали уже после
 * входа — и часть людей так и оставалась с неподтверждённым адресом.
 * Теперь до анкеты не пройти без верного кода.
 */
class RegistrationStepsTest extends TestCase
{
    use LegalRegistration;
    use RefreshDatabase;

    private function sentCode(string $email): string
    {
        $code = null;

        Notification::assertSentTo(
            new AnonymousNotifiable,
            RegisterEmailCode::class,
            function (RegisterEmailCode $n, array $channels, AnonymousNotifiable $to) use ($email, &$code): bool {
                $code = $n->code;

                return $to->routes['mail'] === $email;
            },
        );

        return (string) $code;
    }

    #[Test]
    public function три_шага_от_почты_до_аккаунта(): void
    {
        Notification::fake();

        // Шаг 1: почта
        $this->get('/register')->assertInertia(fn (AssertableInertia $p) => $p->component('auth/RegisterEmail'));

        $this->post('/register/email', ['email' => 'rustam@company.uz'])
            ->assertRedirect('/register/code')
            ->assertSessionHasNoErrors();

        $code = $this->sentCode('rustam@company.uz');
        $this->assertMatchesRegularExpression('/^\d{6}$/', $code);

        // Шаг 2: код
        $this->get('/register/code')->assertInertia(fn (AssertableInertia $p) => $p
            ->component('auth/RegisterCode')
            ->where('email', 'rustam@company.uz'));

        $this->post('/register/code', ['code' => $code])->assertRedirect('/register/details');

        // Шаг 3: анкета — почта в ней уже подтверждённая
        $this->get('/register/details')->assertInertia(fn (AssertableInertia $p) => $p
            ->component('auth/Register')
            ->where('email', 'rustam@company.uz')
            ->has('categories'));

        $this->post('/register', [
            'name' => 'Рустам Каримов',
            'phone' => '+998 90 123-45-67',
            'password' => 'Cement2026x',
            'password_confirmation' => 'Cement2026x',
            'terms' => true,
            ...$this->legalFields(),
        ])->assertRedirect('/onboarding/company')->assertSessionHasNoErrors();

        $user = User::where('email', 'rustam@company.uz')->firstOrFail();

        $this->assertTrue($user->hasVerifiedEmail());
        $this->assertAuthenticatedAs($user);
        // Второе письмо «подтвердите почту» не нужно
        Notification::assertNotSentTo($user, VerifyEmailCode::class);
    }

    #[Test]
    public function неверный_код_не_пускает_на_третий_шаг(): void
    {
        Notification::fake();

        $this->post('/register/email', ['email' => 'rustam@company.uz']);
        $code = $this->sentCode('rustam@company.uz');
        $wrong = $code === '111111' ? '222222' : '111111';

        $this->from('/register/code')
            ->post('/register/code', ['code' => $wrong])
            ->assertRedirect('/register/code')
            ->assertSessionHasErrors('code');

        $this->get('/register/details')->assertRedirect('/register/code');
    }

    #[Test]
    public function без_почты_шаги_два_и_три_ведут_на_первый(): void
    {
        $this->get('/register/code')->assertRedirect('/register');
        $this->get('/register/details')->assertRedirect('/register');
        $this->post('/register/code', ['code' => '123456'])->assertRedirect('/register');
    }

    /** Анкету без подтверждённой почты не принять, даже подставив адрес в форму. */
    #[Test]
    public function анкета_без_кода_не_создаёт_аккаунт(): void
    {
        $this->post('/register', [
            'email' => 'chuzhoy@company.uz',
            'name' => 'Рустам Каримов',
            'phone' => '+998 90 123-45-67',
            'password' => 'Cement2026x',
            'password_confirmation' => 'Cement2026x',
            'terms' => true,
            ...$this->legalFields(),
        ])->assertRedirect('/register');

        $this->assertSame(0, User::query()->count());
    }

    /** Код подтверждал один адрес — сменив почту на первом шаге, его не использовать. */
    #[Test]
    public function смена_почты_сбрасывает_подтверждение(): void
    {
        Notification::fake();

        $this->post('/register/email', ['email' => 'rustam@company.uz']);
        $this->post('/register/code', ['code' => $this->sentCode('rustam@company.uz')])
            ->assertRedirect('/register/details');

        $this->post('/register/email', ['email' => 'drugoy@company.uz'])->assertRedirect('/register/code');

        $this->get('/register/details')->assertRedirect('/register/code');
    }

    #[Test]
    public function повторная_отправка_выпускает_новый_код(): void
    {
        Notification::fake();

        $this->post('/register/email', ['email' => 'rustam@company.uz']);
        $first = $this->sentCode('rustam@company.uz');

        $this->from('/register/code')
            ->post('/register/code/resend')
            ->assertRedirect('/register/code')
            ->assertSessionHas('status');

        Notification::assertSentTimes(RegisterEmailCode::class, 2);

        $this->get('/register/code')->assertInertia(fn (AssertableInertia $p) => $p->where('status', __('ui.messages.auth.mail_resent')));
        $this->assertNotSame('', $first);
    }

    /** «Изменить почту» со второго шага — адрес уже в поле. */
    #[Test]
    public function первый_шаг_помнит_введённую_почту(): void
    {
        Notification::fake();

        $this->post('/register/email', ['email' => 'rustam@company.uz']);

        $this->get('/register')->assertInertia(fn (AssertableInertia $p) => $p
            ->component('auth/RegisterEmail')
            ->where('email', 'rustam@company.uz'));
    }
}
