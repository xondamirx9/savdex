<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Models\User;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Право удалять данные — только у суперадмина.
 *
 * Компании и объявления модератор видит: это его работа. Но удаление
 * не переопределялось, а Filament без политики разрешает всё — модератор
 * мог выделить полсотни компаний галочками и снести их вместе с
 * кошельками, подписками и оплаченными раскрытиями.
 *
 * Сами разделы теперь на Python (python/tests/test_companies_admin.py,
 * test_listings_admin.py) и спрашивают те же права; здесь — матрица.
 */
class AdminDeletionRightsTest extends TestCase
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

    #[Test]
    public function модератор_не_удаляет_компании_и_объявления(): void
    {
        $moderator = $this->admin(User::ADMIN_MODERATOR);
        $this->actingAs($moderator);

        $this->assertFalse(AdminAccess::allows('companies.delete'));
        $this->assertFalse(AdminAccess::allows('listings.delete'));

        // Окончательное удаление — только суперадмину
        $this->assertFalse($moderator->isSuperadmin());
    }

    /** Модерация остаётся доступной: разделы он по-прежнему видит и правит. */
    #[Test]
    public function модератор_сохраняет_свои_права(): void
    {
        $this->actingAs($this->admin(User::ADMIN_MODERATOR));

        $this->assertTrue(AdminAccess::allows('companies.view'));
        $this->assertTrue(AdminAccess::allows('listings.view'));
        $this->assertTrue(AdminAccess::allows('listings.edit'));
    }

    #[Test]
    public function суперадмин_удалять_может(): void
    {
        $superadmin = $this->admin(User::ADMIN_SUPERADMIN);
        $this->actingAs($superadmin);

        $this->assertTrue(AdminAccess::allows('companies.delete'));
        $this->assertTrue(AdminAccess::allows('listings.delete'));
        $this->assertTrue($superadmin->isSuperadmin());
    }
}
