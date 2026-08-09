<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Models\User;
use Filament\Facades\Filament;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Выдача доступа в админку из консоли.
 *
 * Сидера с готовым администратором нет намеренно: учётка с известным
 * паролем, приехавшая на прод вместе с демо-данными, — открытая дверь.
 */
class MakeAdminCommandTest extends TestCase
{
    use RefreshDatabase;

    #[Test]
    public function команда_создаёт_суперадмина(): void
    {
        $this->artisan('savdex:admin', ['email' => 'boss@savdex.uz', '--password' => 'Savdex2026!x'])
            ->assertSuccessful();

        $user = User::where('email', 'boss@savdex.uz')->firstOrFail();

        $this->assertTrue($user->isSuperadmin());
        $this->assertTrue($user->canAccessPanel(Filament::getPanel('admin')));
        $this->assertNotNull($user->email_verified_at, 'админ не должен спотыкаться о собственные проверки');
        $this->assertTrue($user->must_change_password);
    }

    /** Роль выдаётся и обычному пользователю — заводить вторую учётку незачем. */
    #[Test]
    public function команда_повышает_существующего_пользователя(): void
    {
        $user = User::factory()->create(['email' => 'moder@savdex.uz']);

        $this->artisan('savdex:admin', ['email' => 'moder@savdex.uz', '--moderator' => true])
            ->assertSuccessful();

        $user->refresh();

        $this->assertTrue($user->isModerator());
        $this->assertFalse($user->isSuperadmin());
        $this->assertSame(1, User::where('email', 'moder@savdex.uz')->count(), 'дубль учётки не создаётся');
    }

    #[Test]
    public function кривой_адрес_не_создаёт_админа(): void
    {
        $this->artisan('savdex:admin', ['email' => 'не-почта'])->assertFailed();

        $this->assertSame(0, User::where('is_admin', true)->count());
    }

    /**
     * Пока выданный пароль не сменён, панель не открывается: его
     * знают двое, и доступ нельзя считать принадлежащим человеку.
     */
    #[Test]
    public function до_смены_пароля_панель_не_открывается(): void
    {
        $admin = User::factory()->create([
            'is_admin' => true,
            'admin_role' => User::ADMIN_SUPERADMIN,
            'status' => 'active',
            'must_change_password' => true,
        ]);

        $this->actingAs($admin)
            ->get('/admin')
            ->assertRedirect(route('password.forced'));
    }
}
