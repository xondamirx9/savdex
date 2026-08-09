<?php

declare(strict_types=1);

namespace Tests\Feature\Auth;

use App\Models\User;
use App\Services\Auth\LoginThrottle;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * NEG-02, NEG-03, NEG-06d, NEG-06f из QA.md — сценарии входа.
 */
class LoginTest extends TestCase
{
    use RefreshDatabase;

    private function user(array $overrides = []): User
    {
        return User::factory()->create(array_merge([
            'email' => 'rustam@company.uz',
            'password' => 'Cement2026!x',
            'status' => 'active',
        ], $overrides));
    }

    #[Test]
    public function страница_входа_открывается(): void
    {
        $this->get('/login')->assertOk();
    }

    #[Test]
    public function верные_данные_пускают_в_кабинет(): void
    {
        $user = $this->user();

        $this->post('/login', ['email' => 'rustam@company.uz', 'password' => 'Cement2026!x'])
            ->assertRedirect('/cabinet');

        $this->assertAuthenticatedAs($user);
    }

    #[Test]
    public function успешный_вход_записывает_время_и_адрес(): void
    {
        $this->user();

        $this->post('/login', ['email' => 'rustam@company.uz', 'password' => 'Cement2026!x']);

        $user = User::first();
        $this->assertNotNull($user->last_login_at);
        $this->assertNotNull($user->last_login_ip);
    }

    /**
     * NEG-06d: по ответу нельзя понять, зарегистрирован адрес или нет.
     * Иначе форма входа превращается в инструмент проверки базы адресов.
     */
    #[Test]
    public function несуществующий_адрес_и_неверный_пароль_дают_одинаковый_ответ(): void
    {
        $this->user();

        // Существующий пользователь, неверный пароль
        $this->post('/login', [
            'email' => 'rustam@company.uz',
            'password' => 'НеверныйПароль1',
        ])->assertInvalid(['email' => 'Неверная почта или пароль']);

        // Незарегистрированный адрес — ответ должен быть тем же самым
        $this->post('/login', [
            'email' => 'never-registered@company.uz',
            'password' => 'НеверныйПароль1',
        ])->assertInvalid(['email' => 'Неверная почта или пароль']);
    }

    #[Test]
    public function сообщение_показывает_остаток_попыток(): void
    {
        $this->user();

        $this->post('/login', ['email' => 'rustam@company.uz', 'password' => 'Неверный1'])
            ->assertInvalid(['email' => 'Осталось попыток: 4 из 5']);
    }

    #[Test]
    public function после_пяти_неудач_вход_блокируется_даже_с_верным_паролем(): void
    {
        $this->user();

        for ($i = 0; $i < LoginThrottle::MAX_ATTEMPTS; $i++) {
            $this->post('/login', ['email' => 'rustam@company.uz', 'password' => 'Неверный1']);
        }

        $this->post('/login', ['email' => 'rustam@company.uz', 'password' => 'Cement2026!x'])
            ->assertInvalid(['email' => 'Слишком много попыток']);

        $this->assertGuest();
    }

    #[Test]
    public function сообщение_о_блокировке_называет_срок(): void
    {
        // «Попробуйте позже» без срока порождает обращения в поддержку
        $this->user();

        for ($i = 0; $i < LoginThrottle::MAX_ATTEMPTS; $i++) {
            $this->post('/login', ['email' => 'rustam@company.uz', 'password' => 'Неверный1']);
        }

        // Точного числа минут не проверяем — важно, что срок вообще назван
        $this->post('/login', ['email' => 'rustam@company.uz', 'password' => 'Неверный1'])
            ->assertInvalid(['email' => 'Попробуйте через']);
    }

    #[Test]
    public function заблокированного_пользователя_не_пускают_с_верным_паролем(): void
    {
        $this->user(['status' => 'blocked']);

        $this->post('/login', ['email' => 'rustam@company.uz', 'password' => 'Cement2026!x'])
            ->assertSessionHasErrors('email');

        $this->assertGuest();
    }

    /** NEG-06f: пароль, выданный суперадмином, обязателен к смене. */
    #[Test]
    public function выданный_админом_пароль_требует_смены_при_первом_входе(): void
    {
        $this->user(['must_change_password' => true]);

        $this->post('/login', ['email' => 'rustam@company.uz', 'password' => 'Cement2026!x'])
            ->assertRedirect('/password/change');
    }

    #[Test]
    public function выход_завершает_сессию(): void
    {
        $this->actingAs($this->user());

        $this->post('/logout')->assertRedirect('/');

        $this->assertGuest();
    }

    #[Test]
    public function гость_не_попадает_в_кабинет(): void
    {
        $this->get('/cabinet')->assertRedirect('/login');
    }

    #[Test]
    public function авторизованного_не_пускают_на_страницу_входа(): void
    {
        $this->actingAs($this->user());

        $this->get('/login')->assertRedirect();
    }
}
