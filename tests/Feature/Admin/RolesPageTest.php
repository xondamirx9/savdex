<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Pages\Roles;
use App\Models\AdminAction;
use App\Models\User;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Экран «Роли и права».
 *
 * Отсюда выдают и отбирают доступ, поэтому проверяется не вёрстка,
 * а три вещи: кто сюда попадает, что происходит с правами и что
 * из этого остаётся в журнале.
 */
class RolesPageTest extends TestCase
{
    use RefreshDatabase;

    private function admin(string $role): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => $role,
            'status' => 'active',
        ]);
    }

    // ── Кто сюда попадает ───────────────────────────────────────────

    #[Test]
    public function экран_открыт_только_суперадмину(): void
    {
        foreach (AdminAccess::ROLES as $role => $label) {
            $this->actingAs($this->admin($role));

            $this->assertSame(
                $role === AdminAccess::SUPERADMIN,
                Roles::canAccess(),
                "роль «{$label}»",
            );
        }
    }

    #[Test]
    public function в_списке_только_сотрудники(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPERADMIN));

        $employee = $this->admin(AdminAccess::MODERATOR);
        $client = User::factory()->create(['is_admin' => false]);

        Livewire::test(Roles::class)
            ->assertCanSeeTableRecords([$employee])
            ->assertCanNotSeeTableRecords([$client]);
    }

    // ── Выдача и отзыв ──────────────────────────────────────────────

    #[Test]
    public function суперадмин_выдаёт_доступ_клиенту(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPERADMIN));

        $client = User::factory()->create(['is_admin' => false]);

        Livewire::test(Roles::class)
            ->callAction('grantAccess', [
                'user_id' => $client->id,
                'admin_role' => AdminAccess::FINANCE,
            ]);

        $client->refresh();

        $this->assertTrue($client->is_admin);
        $this->assertSame(AdminAccess::FINANCE, $client->admin_role);
        $this->assertTrue($client->hasAdminAbility('payments.edit'));
    }

    #[Test]
    public function смена_роли_меняет_права(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPERADMIN));

        $employee = $this->admin(AdminAccess::MODERATOR);

        $this->assertFalse($employee->hasAdminAbility('payments.view'));

        Livewire::test(Roles::class)
            ->callTableAction('changeRole', $employee, ['admin_role' => AdminAccess::FINANCE]);

        $this->assertTrue($employee->fresh()->hasAdminAbility('payments.view'));
    }

    #[Test]
    public function личное_право_выдаётся_с_экрана(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPERADMIN));

        $employee = $this->admin(AdminAccess::ADMIN);

        Livewire::test(Roles::class)
            ->callTableAction('personalRights', $employee, [
                'grant' => ['payments.view'],
                'revoke' => ['companies.create'],
            ]);

        $employee->refresh();

        $this->assertTrue($employee->hasAdminAbility('payments.view'), 'выданное появилось');
        $this->assertFalse($employee->hasAdminAbility('companies.create'), 'отозванное пропало');
    }

    #[Test]
    public function отключение_доступа_сохраняет_роль(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPERADMIN));

        $employee = $this->admin(AdminAccess::MODERATOR);

        Livewire::test(Roles::class)
            ->callTableAction('revokeAccess', $employee);

        $employee->refresh();

        $this->assertFalse($employee->is_admin);
        $this->assertSame(AdminAccess::MODERATOR, $employee->admin_role, 'роль осталась на случай возврата');
        $this->assertFalse($employee->hasAdminAbility('listings.moderate'));
    }

    // ── Защита от самоотключения ────────────────────────────────────

    /**
     * Панель без владельца чинится только руками в базе, и обнаружится
     * это в тот момент, когда понадобится что-то срочно поправить.
     */
    #[Test]
    public function последнего_суперадмина_нельзя_понизить(): void
    {
        $only = $this->admin(AdminAccess::SUPERADMIN);
        $this->actingAs($only);

        Livewire::test(Roles::class)
            ->callTableAction('changeRole', $only, ['admin_role' => AdminAccess::SUPPORT]);

        $this->assertSame(AdminAccess::SUPERADMIN, $only->fresh()->admin_role);
    }

    #[Test]
    public function последнего_суперадмина_нельзя_отключить(): void
    {
        $only = $this->admin(AdminAccess::SUPERADMIN);
        $this->actingAs($only);

        Livewire::test(Roles::class)
            ->callTableAction('revokeAccess', $only);

        $this->assertTrue($only->fresh()->is_admin);
    }

    #[Test]
    public function при_втором_суперадмине_понижение_проходит(): void
    {
        $first = $this->admin(AdminAccess::SUPERADMIN);
        $second = $this->admin(AdminAccess::SUPERADMIN);

        $this->actingAs($first);

        Livewire::test(Roles::class)
            ->callTableAction('changeRole', $second, ['admin_role' => AdminAccess::SUPPORT]);

        $this->assertSame(AdminAccess::SUPPORT, $second->fresh()->admin_role);
    }

    // ── След в журнале ──────────────────────────────────────────────

    /** Выдача и отзыв прав — первое, что смотрят при разборе инцидента. */
    #[Test]
    public function выдача_доступа_попадает_в_журнал(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPERADMIN));

        $client = User::factory()->create(['is_admin' => false]);

        Livewire::test(Roles::class)
            ->callAction('grantAccess', [
                'user_id' => $client->id,
                'admin_role' => AdminAccess::SALES,
            ]);

        $entry = AdminAction::where('section', 'roles')->where('action', 'granted')->sole();

        $this->assertSame($client->id, $entry->subject_id);
        $this->assertStringContainsString('Отдел продаж', (string) $entry->note);
    }

    #[Test]
    public function отзыв_доступа_попадает_в_журнал(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPERADMIN));

        $employee = $this->admin(AdminAccess::MODERATOR);

        Livewire::test(Roles::class)->callTableAction('revokeAccess', $employee);

        $this->assertTrue(
            AdminAction::where('section', 'roles')->where('action', 'revoked')->exists(),
        );
    }
}
