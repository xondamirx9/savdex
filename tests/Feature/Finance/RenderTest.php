<?php

declare(strict_types=1);

namespace Tests\Feature\Finance;

use App\Filament\Pages\FinanceOperations;
use App\Filament\Pages\Roles;
use App\Filament\Resources\AdminActions\Pages\ListAdminActions;
use App\Filament\Resources\Communications\Pages\ListCommunications;
use App\Filament\Resources\Contacts\Pages\ListContacts;
use App\Filament\Resources\Deals\Pages\ListDeals;
use App\Filament\Resources\Leads\Pages\ListLeads;
use App\Filament\Resources\Refunds\Pages\ListRefunds;
use App\Filament\Resources\Tasks\Pages\ListTasks;
use App\Filament\Resources\Tickets\Pages\ListTickets;
use App\Models\User;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Каждая новая страница обязана открываться.
 *
 * Тест дешёвый и скучный, но ловит целый класс поломок, который иначе
 * находит пользователь: опечатку в колонке, связь без модели, вид,
 * которого нет. Один раз так и вышло — Filament подставляет аргументы
 * замыкания по имени параметра, и $q вместо $query ронял страницу при
 * первом же фильтре.
 */
class RenderTest extends TestCase
{
    use RefreshDatabase;

    /**
     * @return array<string, array{class-string}>
     */
    public static function страницы(): array
    {
        return [
            'журнал действий' => [ListAdminActions::class],
            'роли и права' => [Roles::class],
            'лиды' => [ListLeads::class],
            'сделки' => [ListDeals::class],
            'контакты' => [ListContacts::class],
            'задачи' => [ListTasks::class],
            'коммуникации' => [ListCommunications::class],
            'обращения' => [ListTickets::class],
            'возвраты' => [ListRefunds::class],
            'финансовые операции' => [FinanceOperations::class],
        ];
    }

    /**
     * @param  class-string  $page
     */
    #[Test]
    #[DataProvider('страницы')]
    public function страница_открывается(string $page): void
    {
        $this->actingAs(User::factory()->create([
            'is_admin' => true,
            'admin_role' => AdminAccess::SUPERADMIN,
            'status' => 'active',
        ]));

        Livewire::test($page)->assertOk();
    }
}
