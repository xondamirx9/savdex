<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Resources\Companies\Pages\ListCompanies;
use App\Filament\Widgets\ActivationFunnel;
use App\Filament\Widgets\ContentDrafts;
use App\Filament\Widgets\FinanceToday;
use App\Filament\Widgets\IntakeQueue;
use App\Filament\Widgets\ModerationQueue;
use App\Filament\Widgets\MyLeads;
use App\Filament\Widgets\MyTasks;
use App\Filament\Widgets\PlatformStats;
use App\Filament\Widgets\RegistrationsChart;
use App\Filament\Widgets\SupportQueue;
use App\Models\Company;
use App\Models\Crm\Lead;
use App\Models\Crm\Task;
use App\Models\User;
use App\Support\AdminAccess;
use Filament\Pages\Dashboard;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Стартовый экран каждой роли.
 *
 * До этого все девять ролей попадали на одну и ту же инфопанель с
 * показателями площадки. Продавец, которому нужны свои лиды, смотрел
 * на воронку активации; модератор, которому нужна очередь, — туда же.
 *
 * Проверяется, что каждый видит своё и не видит чужого.
 */
class DashboardTest extends TestCase
{
    use RefreshDatabase;

    private function actAs(string $role): User
    {
        $user = User::factory()->create([
            'is_admin' => true,
            'admin_role' => $role,
            'status' => 'active',
        ]);

        $this->actingAs($user);

        return $user;
    }

    /**
     * Что каждая роль видит на стартовом экране.
     *
     * Списки записаны руками: тест, выводящий ожидание из той же
     * матрицы, что и проверяемый код, не проверяет ничего.
     *
     * @return array<string, array{string, list<class-string>}>
     */
    public static function виджетыРолей(): array
    {
        $platform = [PlatformStats::class, ActivationFunnel::class, RegistrationsChart::class];

        return [
            // Суперадмину видно понемногу от каждой роли: он один
            // отвечает за всё и должен замечать, где встало, не обходя
            // разделы по очереди
            'суперадмин' => [AdminAccess::SUPERADMIN, [
                MyLeads::class, MyTasks::class, IntakeQueue::class,
                ModerationQueue::class, SupportQueue::class,
                FinanceToday::class, ContentDrafts::class,
                ...$platform,
            ]],

            'администратор' => [AdminAccess::ADMIN, [
                MyLeads::class, MyTasks::class, SupportQueue::class, ContentDrafts::class,
                ...$platform,
            ]],

            'продажи' => [AdminAccess::SALES, [MyLeads::class, MyTasks::class]],

            'менеджер поставщиков' => [AdminAccess::SUPPLIER_MANAGER, [
                MyLeads::class, MyTasks::class, IntakeQueue::class,
            ]],

            'менеджер покупателей' => [AdminAccess::BUYER_MANAGER, [
                MyLeads::class, MyTasks::class, IntakeQueue::class,
            ]],

            'модератор' => [AdminAccess::MODERATOR, [ModerationQueue::class]],

            'финансы' => [AdminAccess::FINANCE, [FinanceToday::class]],

            'поддержка' => [AdminAccess::SUPPORT, [MyTasks::class, SupportQueue::class]],

            'контент' => [AdminAccess::CONTENT_MANAGER, [ContentDrafts::class]],
        ];
    }

    /**
     * @param  list<class-string>  $expected
     */
    #[Test]
    #[DataProvider('виджетыРолей')]
    public function роль_видит_свои_виджеты(string $role, array $expected): void
    {
        $this->actAs($role);

        $all = [
            MyLeads::class, MyTasks::class, IntakeQueue::class, ModerationQueue::class,
            SupportQueue::class, FinanceToday::class, ContentDrafts::class,
            PlatformStats::class, ActivationFunnel::class, RegistrationsChart::class,
        ];

        foreach ($all as $widget) {
            $this->assertSame(
                in_array($widget, $expected, true),
                $widget::canView(),
                class_basename($widget)." у роли «{$role}»",
            );
        }
    }

    /**
     * Суперадмин видит по кусочку от каждой роли.
     *
     * Он один отвечает за всё сразу, и обходить девять разделов, чтобы
     * понять, где встало, — не работа, а ритуал.
     */
    #[Test]
    public function суперадмин_видит_виджеты_всех_ролей(): void
    {
        $this->actAs(AdminAccess::SUPERADMIN);

        foreach ([
            MyLeads::class, MyTasks::class, IntakeQueue::class, ModerationQueue::class,
            SupportQueue::class, FinanceToday::class, ContentDrafts::class,
            PlatformStats::class, ActivationFunnel::class, RegistrationsChart::class,
        ] as $widget) {
            $this->assertTrue($widget::canView(), class_basename($widget));
        }
    }

    /**
     * Выручка площадки — не всем.
     *
     * Продавец, модератор, поддержка и контент-менеджер в границах роли
     * финансовой аналитики не видят, а инфопанель была у всех общая.
     */
    #[Test]
    public function показатели_площадки_видят_только_руководящие_роли(): void
    {
        foreach (AdminAccess::ROLES as $role => $label) {
            $this->actAs($role);

            $expected = in_array($role, [AdminAccess::SUPERADMIN, AdminAccess::ADMIN], true);

            $this->assertSame($expected, PlatformStats::canView(), $label);
        }
    }

    #[Test]
    public function дашборд_открывается_у_каждой_роли(): void
    {
        foreach (array_keys(AdminAccess::ROLES) as $role) {
            $user = $this->actAs($role);

            Lead::factory()->create(['owner_id' => $user->id]);
            Task::factory()->create(['assignee_id' => $user->id, 'due_at' => now()]);
            Company::factory()->create(['primary_role' => 'supplier']);

            Livewire::test(Dashboard::class)->assertOk();
        }
    }

    // ── Вкладки компаний ────────────────────────────────────────────

    #[Test]
    public function вкладки_делят_компании_по_направлению(): void
    {
        $this->actAs(AdminAccess::SUPERADMIN);

        $supplier = Company::factory()->create(['primary_role' => 'supplier']);
        $buyer = Company::factory()->create(['primary_role' => 'buyer']);
        $both = Company::factory()->create(['primary_role' => 'both']);

        Livewire::test(ListCompanies::class)
            ->set('activeTab', 'suppliers')
            ->assertCanSeeTableRecords([$supplier, $both])
            ->assertCanNotSeeTableRecords([$buyer]);

        Livewire::test(ListCompanies::class)
            ->set('activeTab', 'buyers')
            ->assertCanSeeTableRecords([$buyer, $both])
            ->assertCanNotSeeTableRecords([$supplier]);
    }

    /** Компания, которая и продаёт, и закупает, нужна обоим менеджерам. */
    #[Test]
    public function компания_с_обеими_ролями_видна_в_обеих_вкладках(): void
    {
        $this->actAs(AdminAccess::SUPERADMIN);

        $both = Company::factory()->create(['primary_role' => 'both']);

        foreach (['suppliers', 'buyers'] as $tab) {
            Livewire::test(ListCompanies::class)
                ->set('activeTab', $tab)
                ->assertCanSeeTableRecords([$both]);
        }
    }

    #[Test]
    public function менеджер_направления_попадает_на_свою_вкладку(): void
    {
        $this->actAs(AdminAccess::SUPPLIER_MANAGER);
        $this->assertSame('suppliers', Livewire::test(ListCompanies::class)->get('activeTab'));

        $this->actAs(AdminAccess::BUYER_MANAGER);
        $this->assertSame('buyers', Livewire::test(ListCompanies::class)->get('activeTab'));

        $this->actAs(AdminAccess::SUPERADMIN);
        $this->assertSame('all', Livewire::test(ListCompanies::class)->get('activeTab'));
    }
}
