<?php

declare(strict_types=1);

namespace Tests\Feature\Auth;

use App\Models\Company;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Кабинет закрыт, пока выданный администратором пароль не заменён.
 *
 * Проверка стояла только на входе: человека один раз уводило на смену
 * пароля, а дальше он набирал /cabinet руками и работал. Временный
 * пароль знают двое — и он давал публикацию объявлений, правку компании
 * и выгрузку купленных контактов.
 */
class ForcedPasswordChangeTest extends TestCase
{
    use RefreshDatabase;

    private function user(bool $mustChange): User
    {
        return User::factory()->for(Company::factory())->create([
            'must_change_password' => $mustChange,
            'email_verified_at' => now(),
        ]);
    }

    /** @return list<array{string}> */
    public static function разделыКабинета(): array
    {
        return [
            ['/cabinet'],
            ['/cabinet/listings'],
            ['/cabinet/contacts'],
            ['/cabinet/contacts/export'],
            ['/cabinet/company'],
            ['/cabinet/billing'],
            ['/cabinet/settings'],
            ['/cabinet/analytics'],
            ['/notifications'],
        ];
    }

    #[Test]
    #[DataProvider('разделыКабинета')]
    public function с_невозвращённым_паролем_разделы_закрыты(string $url): void
    {
        $this->actingAs($this->user(mustChange: true))
            ->get($url)
            ->assertRedirect(route('password.forced'));
    }

    #[Test]
    #[DataProvider('разделыКабинета')]
    public function после_смены_пароля_разделы_открыты(string $url): void
    {
        $this->actingAs($this->user(mustChange: false))
            ->get($url)
            ->assertSuccessful();
    }

    /** Выход должен работать всегда — иначе человек заперт на одном экране. */
    #[Test]
    public function выход_доступен_и_с_невозвращённым_паролем(): void
    {
        $this->actingAs($this->user(mustChange: true))
            ->post('/logout')
            ->assertRedirect();

        $this->assertGuest();
    }

    /**
     * Панель хранит в сессии хеш пароля (AuthenticateSession), и
     * контроллер обязан обновить его вместе с паролем — иначе первый
     * же переход в /admin разлогинивает, и администратор ходит по
     * кругу «вход → смена пароля → снова вход».
     */
    #[Test]
    public function смена_пароля_не_разлогинивает_администратора_в_панели(): void
    {
        $admin = User::factory()->create([
            'is_admin' => true,
            'admin_role' => User::ADMIN_SUPERADMIN,
            'must_change_password' => true,
            'email_verified_at' => now(),
            'status' => 'active',
        ]);
        $oldHash = $admin->getAuthPassword();

        $this->actingAs($admin)
            ->withSession(['password_hash_web' => $oldHash])
            ->post('/password/change', [
                'password' => 'Sovsem-Novy-2026!',
                'password_confirmation' => 'Sovsem-Novy-2026!',
            ])
            ->assertRedirect('/admin');

        $this->assertNotSame($oldHash, session('password_hash_web'));

        $this->get('/admin')->assertOk();
    }

    #[Test]
    public function экран_смены_пароля_не_зацикливается(): void
    {
        $this->actingAs($this->user(mustChange: true))
            ->get('/password/change')
            ->assertSuccessful();
    }

    /** Публикация объявления временным паролем — тот самый угон аккаунта. */
    #[Test]
    public function публиковать_объявления_нельзя(): void
    {
        $user = $this->user(mustChange: true);

        $this->actingAs($user)
            ->get('/cabinet/listings/create')
            ->assertRedirect(route('password.forced'));
    }
}
