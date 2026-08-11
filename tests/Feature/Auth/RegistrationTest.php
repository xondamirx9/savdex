<?php

declare(strict_types=1);

namespace Tests\Feature\Auth;

use App\Models\User;
use Illuminate\Auth\Events\Registered;
use Illuminate\Auth\Notifications\VerifyEmail;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Event;
use Illuminate\Support\Facades\Notification;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * NEG-01, NEG-04, NEG-06b, NEG-06c из QA.md — валидация регистрации.
 */
class RegistrationTest extends TestCase
{
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
        Event::fake();

        // Второй шаг регистрации — данные компании (пропускаемый),
        // подтверждение почты идёт после него
        $this->post('/register', $this->validPayload())
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
        $this->post('/register', [])
            ->assertSessionHasErrors(['name', 'email', 'phone', 'password', 'terms']);
    }

    #[Test]
    public function пароль_хранится_только_хешем(): void
    {
        $this->post('/register', $this->validPayload());

        $user = User::where('email', 'rustam@company.uz')->first();

        $this->assertNotSame('Cement2026!x', $user->password);
        $this->assertTrue(password_verify('Cement2026!x', $user->password));
    }

    #[Test]
    public function почта_приводится_к_нижнему_регистру(): void
    {
        // Иначе Rustam@Company.uz и rustam@company.uz станут разными аккаунтами
        $this->post('/register', $this->validPayload(['email' => '  Rustam@Company.UZ  ']));

        $this->assertDatabaseHas('users', ['email' => 'rustam@company.uz']);
    }

    #[Test]
    public function повторная_регистрация_на_занятый_адрес_предлагает_выход(): void
    {
        User::factory()->create(['email' => 'rustam@company.uz']);

        $response = $this->post('/register', $this->validPayload());

        $response->assertSessionHasErrors('email');

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
        $this->post('/register', $this->validPayload(['email' => $email]))
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
        $this->post('/register', $this->validPayload([
            'password' => 'Cem2026',
            'password_confirmation' => 'Cem2026',
        ]))->assertSessionHasErrors('password');
    }

    #[Test]
    public function несовпадающие_пароли_отклоняются(): void
    {
        $this->post('/register', $this->validPayload([
            'password_confirmation' => 'ДругойПароль2026!',
        ]))->assertSessionHasErrors('password');
    }

    #[Test]
    public function без_согласия_с_офертой_регистрация_невозможна(): void
    {
        $this->post('/register', $this->validPayload(['terms' => false]))
            ->assertSessionHasErrors('terms');

        $this->assertDatabaseCount('users', 0);
    }

    #[Test]
    public function короткий_телефон_отклоняется(): void
    {
        $this->post('/register', $this->validPayload(['phone' => '123']))
            ->assertSessionHasErrors('phone');
    }

    #[Test]
    public function новый_пользователь_не_может_действовать_до_подтверждения_почты(): void
    {
        $this->post('/register', $this->validPayload());

        $user = User::where('email', 'rustam@company.uz')->first();

        $this->assertFalse($user->hasVerifiedEmail());
        $this->assertFalse($user->canAct(), 'Публикация и раскрытие контактов должны быть заблокированы');
    }

    /**
     * Демо-стенд без почтового сервиса: адрес подтверждается сразу,
     * письмо не отправляется (см. demo_auto_verify в config/app.php).
     */
    #[Test]
    public function демо_режим_подтверждает_почту_при_регистрации_без_письма(): void
    {
        config(['app.demo_auto_verify' => true]);
        Notification::fake();

        $this->post('/register', $this->validPayload());

        $user = User::where('email', 'rustam@company.uz')->first();

        $this->assertTrue($user->hasVerifiedEmail());
        Notification::assertNotSentTo($user, VerifyEmail::class);
    }

    /**
     * Правило confirmed вешает ошибку только на password, и подпись
     * «Пароли не совпадают» появлялась под первым полем — хотя ошибся
     * человек во втором. Сообщение должно быть у обоих.
     */
    #[Test]
    public function несовпадение_паролей_подсвечивает_поле_повтора(): void
    {
        $this->post('/register', $this->validPayload([
            'password' => 'Parol-12345',
            'password_confirmation' => 'Parol-54321',
        ]))->assertSessionHasErrors([
            'password' => 'Пароли не совпадают',
            'password_confirmation' => 'Пароли не совпадают',
        ]);
    }
}
