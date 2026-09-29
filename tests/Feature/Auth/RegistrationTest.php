<?php

declare(strict_types=1);

namespace Tests\Feature\Auth;

use App\Http\Controllers\Auth\RegisteredUserController;
use App\Models\User;
use Illuminate\Auth\Events\Registered;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Facades\Event;
use Illuminate\Support\Facades\Notification;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\Support\LegalRegistration;
use Tests\TestCase;

/**
 * NEG-01, NEG-04, NEG-06b, NEG-06c из QA.md — валидация регистрации.
 */
class RegistrationTest extends TestCase
{
    use LegalRegistration;
    use RefreshDatabase;

    /** @return array<string, mixed> */
    private function validPayload(array $overrides = []): array
    {
        return array_merge([
            'name' => 'Рустам Каримов',
            'email' => 'rustam@company.uz',
            'phone' => '+998 90 123-45-67',
            'password' => 'Cement2026!x',
            'password_confirmation' => 'Cement2026!x',
            'terms' => true,
            ...$this->legalFields(),
        ], $overrides);
    }

    #[Test]
    public function страница_регистрации_открывается(): void
    {
        $this->get('/register')->assertOk();
    }

    #[Test]
    public function корректные_данные_создают_пользователя(): void
    {
        // Только событие регистрации: полная подмена событий отключила бы
        // и события модели, а на них держится адрес (slug) компании
        Event::fake([Registered::class]);

        // Второй шаг регистрации — данные компании (пропускаемый),
        // подтверждение почты идёт после него
        $this->postRegistration($this->validPayload())
            ->assertRedirect('/onboarding/company');

        $user = User::where('email', 'rustam@company.uz')->first();

        $this->assertNotNull($user);
        $this->assertSame(User::ROLE_OWNER, $user->company_role);
        $this->assertAuthenticatedAs($user);

        Event::assertDispatched(Registered::class);
    }

    #[Test]
    public function пустая_форма_подсвечивает_все_обязательные_поля(): void
    {
        // Почта подтверждена на первых шагах — в анкете её поля нет
        $this->postRegistration(['email' => 'rustam@company.uz'])
            ->assertSessionHasErrors(['name', 'phone', 'password', 'terms']);
    }

    #[Test]
    public function пароль_хранится_только_хешем(): void
    {
        $this->postRegistration($this->validPayload());

        $user = User::where('email', 'rustam@company.uz')->first();

        $this->assertNotSame('Cement2026!x', $user->password);
        $this->assertTrue(password_verify('Cement2026!x', $user->password));
    }

    #[Test]
    public function почта_приводится_к_нижнему_регистру(): void
    {
        // Иначе Rustam@Company.uz и rustam@company.uz станут разными аккаунтами
        Notification::fake();

        $this->post('/register/email', ['email' => '  Rustam@Company.UZ  '])->assertRedirect('/register/code');

        $this->assertSame('rustam@company.uz', session(RegisteredUserController::SESSION_EMAIL));
    }

    #[Test]
    public function повторная_регистрация_на_занятый_адрес_предлагает_выход(): void
    {
        User::factory()->create(['email' => 'rustam@company.uz']);

        // Занятый адрес отклоняется на первом шаге, до письма с кодом
        Notification::fake();

        $response = $this->post('/register/email', ['email' => 'rustam@company.uz']);

        $response->assertSessionHasErrors('email');
        Notification::assertNothingSent();

        $message = session('errors')->first('email');
        $this->assertStringContainsString('уже зарегистрирована', $message);
        // Правило 8 из §1 QA.md: у ошибки должен быть выход, а не тупик
        $this->assertStringContainsString('Войдите', $message);
    }

    /**
     * NEG-06b: «нет собаки» и «адрес неполный» — разные ошибки,
     * подсказки должны различаться.
     */
    #[Test]
    #[DataProvider('плохиеАдреса')]
    public function сообщение_об_ошибке_почты_зависит_от_того_что_введено(
        string $email,
        string $expected,
    ): void {
        $this->post('/register/email', ['email' => $email])
            ->assertSessionHasErrors('email');

        $this->assertStringContainsString($expected, session('errors')->first('email'));
    }

    /** @return array<string, array{string, string}> */
    public static function плохиеАдреса(): array
    {
        return [
            'без собаки' => ['rustam', 'не хватает знака @'],
            'без домена' => ['rustam@', 'адрес неполный'],
        ];
    }

    #[Test]
    public function короткий_пароль_отклоняется(): void
    {
        $this->postRegistration($this->validPayload([
            'password' => 'Cem2026',
            'password_confirmation' => 'Cem2026',
        ]))->assertSessionHasErrors('password');
    }

    #[Test]
    public function несовпадающие_пароли_отклоняются(): void
    {
        $this->postRegistration($this->validPayload([
            'password_confirmation' => 'ДругойПароль2026!',
        ]))->assertSessionHasErrors('password');
    }

    #[Test]
    public function без_согласия_с_офертой_регистрация_невозможна(): void
    {
        $this->postRegistration($this->validPayload(['terms' => false]))
            ->assertSessionHasErrors('terms');

        $this->assertDatabaseCount('users', 0);
    }

    #[Test]
    public function короткий_телефон_отклоняется(): void
    {
        $this->postRegistration($this->validPayload(['phone' => '123']))
            ->assertSessionHasErrors('phone');
    }

    #[Test]
    public function почта_подтверждена_кодом_до_анкеты_и_аккаунт_сразу_действует(): void
    {
        $this->postRegistration($this->validPayload());

        $user = User::where('email', 'rustam@company.uz')->first();

        $this->assertTrue($user->hasVerifiedEmail());
        $this->assertTrue($user->canAct());
    }

    /**
     * Демо-стенд без почтового сервиса: письмо не отправляется, а код
     * подставляется на втором шаге (см. demo_auto_verify в config/app.php).
     */
    #[Test]
    public function демо_режим_показывает_код_на_втором_шаге_без_письма(): void
    {
        config(['app.demo_auto_verify' => true]);
        Notification::fake();

        $this->post('/register/email', ['email' => 'rustam@company.uz'])->assertRedirect('/register/code');

        Notification::assertNothingSent();
        $this->get('/register/code')->assertInertia(fn (AssertableInertia $page) => $page
            ->component('auth/RegisterCode')
            ->where('demoCode', fn (?string $code): bool => (bool) preg_match('/^\d{6}$/', (string) $code)),
        );
    }

    /**
     * Правило confirmed вешает ошибку только на password, и подпись
     * «Пароли не совпадают» появлялась под первым полем — хотя ошибся
     * человек во втором. Сообщение должно быть у обоих.
     */
    #[Test]
    public function несовпадение_паролей_подсвечивает_поле_повтора(): void
    {
        $this->postRegistration($this->validPayload([
            'password' => 'Parol-12345',
            'password_confirmation' => 'Parol-54321',
        ]))->assertSessionHasErrors([
            'password' => 'Пароли не совпадают',
            'password_confirmation' => 'Пароли не совпадают',
        ]);
    }

    /**
     * Ошибки ввода не расходуют лимит регистраций с адреса. Раньше
     * лимит (5 в час) считал отправки формы: пять поправок пароля и
     * телефона — и шестая, уже верная, отклонялась на час.
     */
    #[Test]
    public function ошибки_ввода_не_расходуют_лимит_регистраций(): void
    {
        Notification::fake();

        foreach (range(1, 8) as $attempt) {
            $this->postRegistration($this->validPayload([
                'password' => 'korot1',
                'password_confirmation' => 'korot1',
            ]))->assertSessionHasErrors('password');
        }

        $this->postRegistration($this->validPayload())
            ->assertRedirect('/onboarding/company');

        $this->assertDatabaseHas('users', ['email' => 'rustam@company.uz']);
    }

    /**
     * Лимит считает созданные аккаунты. Упёршийся в него видит причину
     * на форме, а не кнопку, которая молча ничего не делает.
     */
    #[Test]
    public function сверх_лимита_аккаунт_не_создаётся_и_причина_видна_на_форме(): void
    {
        Notification::fake();

        foreach (range(1, RegisteredUserController::MAX_PER_HOUR) as $i) {
            $this->postRegistration($this->validPayload(['email' => "user{$i}@company.uz"]))
                ->assertRedirect('/onboarding/company');

            Auth::logout();
        }

        $this->from('/register/details')
            ->postRegistration($this->validPayload(['email' => 'lishniy@company.uz']))
            ->assertRedirect('/register/details')
            ->assertSessionHas('error');

        $this->assertDatabaseMissing('users', ['email' => 'lishniy@company.uz']);

        $this->get('/register/details')->assertInertia(fn (AssertableInertia $page) => $page
            ->component('auth/Register')
            ->where('flash.error', fn (?string $error): bool => str_contains((string) $error, 'Попробуйте через')),
        );
    }
}
