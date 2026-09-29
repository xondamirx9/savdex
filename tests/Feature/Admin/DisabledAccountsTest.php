<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Resources\Users\Pages\EditUser;
use App\Filament\Resources\Users\Pages\ListUsers;
use App\Models\AdminAction;
use App\Models\Favorite;
use App\Models\Listing;
use App\Models\User;
use App\Support\AdminAccess;
use Filament\Actions\Testing\TestAction;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Notification;
use Livewire\Livewire;
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

        $this->post('/register', $this->registration('sher@company.uz'))
            ->assertRedirect('/onboarding/company');

        $this->assertSame(1, User::query()->where('email', 'sher@company.uz')->count(), 'новый аккаунт');
        $this->assertTrue($old->fresh()->trashed(), 'отключённый остаётся в базе');
    }

    #[Test]
    public function действующий_аккаунт_адрес_по_прежнему_держит(): void
    {
        User::factory()->create(['email' => 'sher@company.uz']);

        $this->post('/register', $this->registration('sher@company.uz'))
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

        $this->post('/register', $this->registration('sher@company.uz'))
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

    // ── Filament ────────────────────────────────────────────────────

    #[Test]
    public function отключённый_находится_по_почте_и_удаляется_навсегда(): void
    {
        $superadmin = $this->admin(AdminAccess::SUPERADMIN);
        $gone = User::factory()->create(['email' => 'inoyatov@company.uz']);
        $listing = Listing::factory()->create(['user_id' => $gone->id]);
        Favorite::query()->create(['user_id' => $gone->id, 'listing_id' => $listing->id]);
        $gone->delete();

        Livewire::actingAs($superadmin)
            ->test(ListUsers::class)
            ->filterTable('trashed', false)
            ->searchTable('inoyatov')
            ->assertCanSeeTableRecords([$gone])
            ->callAction(TestAction::make('forceDelete')->table($gone));

        $this->assertNull(User::withTrashed()->find($gone->id));
        $this->assertSame(0, Favorite::query()->where('user_id', $gone->id)->count(), 'личное — вместе с аккаунтом');
        $this->assertNull($listing->fresh()->user_id, 'объявление компании остаётся');
        $this->assertTrue(
            AdminAction::query()->where('section', 'users')->where('action', 'force_deleted')->exists(),
            'в журнале — удаление навсегда, а не просто удаление',
        );
    }

    #[Test]
    public function действующий_в_пачке_навсегда_не_удаляется(): void
    {
        $superadmin = $this->admin(AdminAccess::SUPERADMIN);
        $live = User::factory()->create();
        $gone = User::factory()->create();
        $gone->delete();

        Livewire::actingAs($superadmin)
            ->test(ListUsers::class)
            ->filterTable('trashed', true)
            ->selectTableRecords([$live->id, $gone->id])
            ->callAction(TestAction::make('forceDelete')->table()->bulk());

        $this->assertNotNull(User::query()->find($live->id), 'действующий остался');
        $this->assertNull(User::withTrashed()->find($gone->id));
    }

    #[Test]
    public function восстановление_из_списка(): void
    {
        $superadmin = $this->admin(AdminAccess::SUPERADMIN);
        $gone = User::factory()->create();
        $gone->delete();

        Livewire::actingAs($superadmin)
            ->test(ListUsers::class)
            ->filterTable('trashed', false)
            ->callAction(TestAction::make('restore')->table($gone));

        $this->assertFalse($gone->fresh()->trashed());
    }

    #[Test]
    public function отключение_из_списка(): void
    {
        $superadmin = $this->admin(AdminAccess::SUPERADMIN);
        $user = User::factory()->create();

        Livewire::actingAs($superadmin)
            ->test(ListUsers::class)
            ->callAction(TestAction::make('delete')->table($user));

        $this->assertTrue($user->fresh()->trashed());
    }

    /**
     * Filament проверяет стандартные действия по политикам, а политики
     * у пользователей нет: «Удалить навсегда» видел любой, кому открыта
     * правка пользователей.
     */
    #[Test]
    public function администратор_не_суперадмин_навсегда_не_удаляет(): void
    {
        $admin = $this->admin(AdminAccess::ADMIN);
        $gone = User::factory()->create();
        $gone->delete();

        Livewire::actingAs($admin)
            ->test(EditUser::class, ['record' => $gone->getRouteKey()])
            ->assertActionHidden('forceDelete')
            ->assertActionHidden('restore');

        Livewire::actingAs($admin)
            ->test(ListUsers::class)
            ->filterTable('trashed', false)
            ->assertActionHidden(TestAction::make('forceDelete')->table($gone));
    }

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

    #[Test]
    public function себя_не_отключить_и_не_удалить(): void
    {
        $superadmin = $this->admin(AdminAccess::SUPERADMIN);

        Livewire::actingAs($superadmin)
            ->test(EditUser::class, ['record' => $superadmin->getRouteKey()])
            ->assertActionHidden('delete');
    }
}
