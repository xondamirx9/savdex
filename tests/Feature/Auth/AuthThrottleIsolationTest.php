<?php

declare(strict_types=1);

namespace Tests\Feature\Auth;

use App\Models\User;
use Illuminate\Auth\Notifications\ResetPassword;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Notification;
use PHPUnit\Framework\Attributes\Test;
use Tests\Support\LegalRegistration;
use Tests\TestCase;

/**
 * Просмотр витрины не расходует лимиты входа, регистрации и пароля.
 *
 * Без приставки ключа у throttle все адреса считали в один счётчик
 * «домен|IP»: шесть карточек компаний за минуту — и «Забыли пароль»
 * отвечал «слишком много действий», письмо не уходило.
 */
class AuthThrottleIsolationTest extends TestCase
{
    use RefreshDatabase;
    use LegalRegistration;

    private function browseCompanies(?User $user = null, int $times = 25): void
    {
        foreach (range(1, $times) as $i) {
            ($user ? $this->actingAs($user) : $this)->get('/companies')->assertOk();
        }
    }

    #[Test]
    public function забыли_пароль_после_просмотра_витрины(): void
    {
        Notification::fake();
        $user = User::factory()->create(['email' => 'rustam@company.uz']);

        $this->browseCompanies();

        $this->post('/forgot-password', ['email' => 'rustam@company.uz'])
            ->assertSessionHas('status')
            ->assertSessionHasNoErrors();

        Notification::assertSentTo($user, ResetPassword::class);
    }

    #[Test]
    public function регистрация_после_просмотра_витрины(): void
    {
        Notification::fake();

        $this->browseCompanies();

        $this->post('/register', [
            'name' => 'Рустам Каримов',
            'email' => 'rustam@company.uz',
            'phone' => '+998 90 123-45-67',
            'password' => 'Cement2026!x',
            'password_confirmation' => 'Cement2026!x',
            'terms' => true,
            ...$this->legalFields(),
        ])->assertRedirect('/onboarding/company');
    }

    #[Test]
    public function вход_после_просмотра_витрины(): void
    {
        User::factory()->create(['email' => 'rustam@company.uz', 'password' => 'Cement2026!x']);

        $this->browseCompanies();

        $this->post('/login', ['email' => 'rustam@company.uz', 'password' => 'Cement2026!x'])
            ->assertRedirect();

        $this->assertAuthenticated();
    }

    #[Test]
    public function код_подтверждения_почты_после_просмотра_витрины(): void
    {
        $user = User::factory()->unverified()->create();

        $this->browseCompanies($user);

        $this->actingAs($user)
            ->withHeaders(['X-Inertia' => 'true'])
            ->from('/verify-email')
            ->post('/verify-email/code', ['code' => '000000'])
            ->assertSessionDoesntHaveErrors('body');
    }
}
