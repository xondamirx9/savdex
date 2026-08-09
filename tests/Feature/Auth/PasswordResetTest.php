<?php

declare(strict_types=1);

namespace Tests\Feature\Auth;

use App\Models\User;
use Illuminate\Auth\Notifications\ResetPassword;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Facades\Notification;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Восстановление пароля от начала до конца.
 *
 * Ручной проход показал, что маршруты и контроллер были написаны,
 * а экраны — нет: /forgot-password отдавал заглушку. Тесты проверяли
 * редиректы и потому молчали. Здесь проверяется и компонент страницы.
 */
class PasswordResetTest extends TestCase
{
    use RefreshDatabase;

    #[Test]
    public function форма_запроса_открывается(): void
    {
        $this->get('/forgot-password')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page->component('auth/ForgotPassword'));
    }

    #[Test]
    public function письмо_уходит_на_существующий_адрес(): void
    {
        Notification::fake();
        $user = User::factory()->create(['email' => 'rustam@company.uz']);

        $this->post('/forgot-password', ['email' => 'rustam@company.uz'])
            ->assertSessionHas('status');

        Notification::assertSentTo($user, ResetPassword::class);
    }

    /**
     * Ответ обязан совпадать с ответом для существующего адреса.
     * Иначе форма превращается в способ узнать, зарегистрирована ли
     * на площадке конкретная компания (NEG-06d из QA.md).
     */
    #[Test]
    public function несуществующий_адрес_даёт_такой_же_ответ(): void
    {
        Notification::fake();

        $this->post('/forgot-password', ['email' => 'nikogo@company.uz'])
            ->assertSessionHas('status', 'Если такой адрес зарегистрирован, письмо со ссылкой уже отправлено.')
            ->assertSessionHasNoErrors();

        Notification::assertNothingSent();
    }

    #[Test]
    public function форма_нового_пароля_открывается_по_ссылке_из_письма(): void
    {
        $this->get('/reset-password/token123?email=rustam%40company.uz')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->component('auth/ResetPassword')
                ->where('token', 'token123')
                ->where('email', 'rustam@company.uz'),
            );
    }

    #[Test]
    public function пароль_меняется_и_подтверждение_доходит_до_формы_входа(): void
    {
        Notification::fake();
        $user = User::factory()->create(['email' => 'rustam@company.uz']);

        $this->post('/forgot-password', ['email' => $user->email]);

        $token = null;
        Notification::assertSentTo($user, ResetPassword::class, function (ResetPassword $n) use (&$token): bool {
            $token = $n->token;

            return true;
        });

        $response = $this->post('/reset-password', [
            'token' => $token,
            'email' => $user->email,
            'password' => 'NovyiParol-2026',
            'password_confirmation' => 'NovyiParol-2026',
        ]);

        $response->assertRedirect('/login')->assertSessionHas('status');

        $this->assertTrue(Hash::check('NovyiParol-2026', $user->fresh()->password));

        /*
         * Ключевая проверка: маршрут /login раньше рендерил страницу
         * без проброса status, и человек возвращался на пустую форму,
         * не понимая, сохранился новый пароль или нет.
         */
        $this->followingRedirects()
            ->post('/reset-password', [
                'token' => $token,
                'email' => $user->email,
                'password' => 'NovyiParol-2026',
                'password_confirmation' => 'NovyiParol-2026',
            ]);

        $this->get('/login')->assertInertia(fn (AssertableInertia $page) => $page->has('status'));
    }

    #[Test]
    public function просроченный_токен_объясняет_причину(): void
    {
        $user = User::factory()->create();

        $this->post('/reset-password', [
            'token' => 'protuhshiy-token',
            'email' => $user->email,
            'password' => 'NovyiParol-2026',
            'password_confirmation' => 'NovyiParol-2026',
        ])->assertSessionHasErrors('email');
    }

    #[Test]
    public function несовпадающие_пароли_не_сохраняются(): void
    {
        $user = User::factory()->create();

        $this->post('/reset-password', [
            'token' => 'token',
            'email' => $user->email,
            'password' => 'NovyiParol-2026',
            'password_confirmation' => 'DrugoiParol-2026',
        ])->assertSessionHasErrors(['password' => 'Пароли не совпадают']);
    }
}
