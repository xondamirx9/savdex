<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Models\Favorite;
use App\Models\Listing;
use App\Models\User;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Notification;
use PHPUnit\Framework\Attributes\Test;
use Tests\Support\LegalRegistration;
use Tests\TestCase;

/**
 * Удаление аккаунта в два шага: отключение освобождает почту, отключённый
 * находится в админке и либо восстанавливается, либо удаляется навсегда.
 *
 * Раньше удалённый аккаунт держил адрес навсегда: регистрация отвечала
 * «адрес занят», вход — «неверный пароль», письмо сброса не уходило.
 */
class DisabledAccountsTest extends TestCase
{
    use LegalRegistration;
    use RefreshDatabase;

    private function admin(string $role): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => $role,
            'status' => 'active',
        ]);
    }

    /** @return array<string, mixed> */
    private function registration(string $email): array
    {
        return [
            'name' => 'Шер Иноятов',
            'email' => $email,
            'phone' => '+998 90 123 45 67',
            'password' => 'NovyiParol2026',
            'password_confirmation' => 'NovyiParol2026',
            'terms' => true,
            ...$this->legalFields(),
        ];
    }

    // ── Почта ───────────────────────────────────────────────────────

    #[Test]
    public function почта_отключённого_аккаунта_свободна_для_регистрации(): void
    {
        Notification::fake();
        $old = User::factory()->create(['email' => 'sher@company.uz']);
        $old->delete();

        $this->postRegistration($this->registration('sher@company.uz'))
            ->assertRedirect('/onboarding/company');

        $this->assertSame(1, User::query()->where('email', 'sher@company.uz')->count(), 'новый аккаунт');
        $this->assertTrue($old->fresh()->trashed(), 'отключённый остаётся в базе');
    }

    #[Test]
    public function действующий_аккаунт_адрес_по_прежнему_держит(): void
    {
        User::factory()->create(['email' => 'sher@company.uz']);

        // Занятый адрес отклоняется уже на первом шаге, до письма с кодом
        $this->post('/register/email', ['email' => 'sher@company.uz'])
            ->assertSessionHasErrors('email');
    }

    #[Test]
    public function удаливший_себя_регистрируется_заново_на_ту_же_почту(): void
    {
        Notification::fake();
        $user = User::factory()->create(['email' => 'sher@company.uz', 'password' => 'StaryiParol2026']);

        $this->actingAs($user)
            ->post('/cabinet/settings/delete', ['password' => 'StaryiParol2026'])
            ->assertRedirect('/');

        $this->postRegistration($this->registration('sher@company.uz'))
            ->assertRedirect('/onboarding/company');
    }

    // ── Модель ──────────────────────────────────────────────────────

    #[Test]
    public function навсегда_удаляется_только_отключённый(): void
    {
        $user = User::factory()->create();

        $this->assertFalse($user->forceDelete(), 'действующий навсегда не удаляется');
        $this->assertNotNull(User::withTrashed()->find($user->id));

        $user->delete();
        $user->forceDelete();

        $this->assertNull(User::withTrashed()->find($user->id));
    }

    #[Test]
    public function занятый_адрес_не_даёт_восстановить(): void
    {
        $old = User::factory()->create(['email' => 'sher@company.uz']);
        $old->delete();
        User::factory()->create(['email' => 'sher@company.uz']);

        $this->assertFalse($old->restore());
        $this->assertTrue($old->fresh()->trashed());
    }

    /**
     * Навсегда удалённый аккаунт уносит личное, а объявление компании
     * остаётся — без ссылки на человека (внешние ключи базы).
     */
    #[Test]
    public function навсегда_удалённый_уносит_личное_а_объявление_остаётся(): void
    {
        $gone = User::factory()->create(['email' => 'inoyatov@company.uz']);
        $listing = Listing::factory()->create(['user_id' => $gone->id]);
        Favorite::query()->create(['user_id' => $gone->id, 'listing_id' => $listing->id]);

        $gone->delete();
        $gone->forceDelete();

        $this->assertNull(User::withTrashed()->find($gone->id));
        $this->assertSame(0, Favorite::query()->where('user_id', $gone->id)->count(), 'личное — вместе с аккаунтом');
        $this->assertNull($listing->fresh()->user_id, 'объявление компании остаётся');
    }

    // ── Админка ─────────────────────────────────────────────────────

    /*
     * Поиск отключённых, «Восстановить», «Удалить навсегда» (только
     * суперадмин, не себя) — раздел «Пользователи» на Python:
     * python/tests/test_users_admin.py.
     */

    /** Пункт меню ведёт в тот же раздел на Python — тем, кто видит пользователей. */
    #[Test]
    public function пункт_меню_ведёт_в_раздел_на_python(): void
    {
        $link = '/admin/python?next=/py/admin/accounts/user/%3Fstate%3Ddisabled';

        $this->actingAs($this->admin(AdminAccess::SUPPORT))
            ->get('/admin')
            ->assertSee($link, false);

        $this->actingAs($this->admin(AdminAccess::FINANCE))
            ->get('/admin')
            ->assertDontSee($link, false);
    }
}
