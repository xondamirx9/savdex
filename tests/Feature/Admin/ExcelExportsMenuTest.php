<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Models\User;
use App\Support\AdminAccess;
use Filament\Facades\Filament;
use Filament\Navigation\NavigationItem;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Пункт меню «Выгрузка в Excel».
 *
 * Сама страница — запуск, история и скачивание книг — переехала в
 * админку Django (шаг 68): её проверяет python/tests/test_exports_page.py.
 * Здесь — кому виден пункт и что прежних адресов Filament больше нет.
 */
class ExcelExportsMenuTest extends TestCase
{
    use RefreshDatabase;

    private function admin(string $role, array $grant = []): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => $role,
            'status' => 'active',
            'admin_permissions' => $grant === [] ? null : ['grant' => $grant],
        ]);
    }

    /** @return array<string, NavigationItem> */
    private function items(): array
    {
        $panel = Filament::getPanel('admin');
        Filament::setCurrentPanel($panel);

        return collect($panel->getNavigation())
            ->flatMap(fn ($group) => $group->getItems())
            ->mapWithKeys(fn (NavigationItem $item): array => [(string) $item->getLabel() => $item])
            ->all();
    }

    #[Test]
    public function суперадмину_пункт_ведёт_в_django(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPERADMIN));

        $this->assertSame('/admin/python?next=/py/admin/exports/',
            $this->items()['Выгрузка в Excel']->getUrl());
    }

    /** В книгах почта и телефоны всех: раздела нет ни в одной роли. */
    #[Test]
    public function ролям_не_виден_выданным_лично_виден(): void
    {
        $this->actingAs($this->admin(AdminAccess::ADMIN));
        $this->assertArrayNotHasKey('Выгрузка в Excel', $this->items());

        $this->actingAs($this->admin(AdminAccess::CONTENT_MANAGER, ['backups.view']));
        $this->assertArrayHasKey('Выгрузка в Excel', $this->items());
    }

    #[Test]
    public function прежних_адресов_filament_нет(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPERADMIN));

        $this->get('/admin/excel-exports')->assertNotFound();
        $this->get('/admin/exports/2026-09-30-100000-aaaa/savdex-companies-2026.xlsx')->assertNotFound();
    }
}
