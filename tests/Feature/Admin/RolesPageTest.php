<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Models\User;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Экран «Роли и права».
 *
 * Отсюда выдают и отбирают доступ. Сам экран — на Python (python/tests/
 * test_roles_admin.py: выдача, смена роли, личные права, отзыв, защита
 * последнего суперадмина, строки журнала). Здесь — кто сюда попадает.
 */
class RolesPageTest extends TestCase
{
    use RefreshDatabase;

    private const LINK = '/admin/python?next=/py/admin/accounts/staffmember/';

    private function admin(string $role): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => $role,
            'status' => 'active',
        ]);
    }

    #[Test]
    public function экран_открыт_только_суперадмину(): void
    {
        foreach (AdminAccess::ROLES as $role => $label) {
            $this->actingAs($this->admin($role));

            $this->assertSame(
                $role === AdminAccess::SUPERADMIN,
                AdminAccess::allows('roles.view'),
                "роль «{$label}»",
            );
        }
    }

    /** Пункт меню ведёт в экран на Python — и только тому, кому он открыт. */
    #[Test]
    public function пункт_меню_видит_только_суперадмин(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPERADMIN))
            ->get('/admin')
            ->assertSee(self::LINK, false);

        $this->actingAs($this->admin(AdminAccess::ADMIN))
            ->get('/admin')
            ->assertDontSee(self::LINK, false);
    }
}
