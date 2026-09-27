<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Models\User;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Пункт меню «Типы компаний».
 *
 * Раздел с этапа 2 переноса работает на Python
 * (python/savdex/catalogs/admin.py, проверки —
 * python/tests/test_company_types_admin.py). Из Filament туда ведёт
 * пункт меню через пропуск, и видеть его должны те же роли, что
 * видели прежний раздел, — у кого есть справочники.
 */
class CompanyTypesMenuTest extends TestCase
{
    use RefreshDatabase;

    private const LINK = '/admin/python?next=/py/admin/catalogs/companytype/';

    /** @return array<string, array{string, bool}> */
    public static function роли(): array
    {
        return [
            'суперадмин' => [AdminAccess::SUPERADMIN, true],
            'администратор' => [AdminAccess::ADMIN, true],
            'модератор' => [AdminAccess::MODERATOR, true],
            'контент' => [AdminAccess::CONTENT_MANAGER, true],
            'продажи' => [AdminAccess::SALES, false],
            'финансы' => [AdminAccess::FINANCE, false],
            'поддержка' => [AdminAccess::SUPPORT, false],
        ];
    }

    #[Test]
    #[DataProvider('роли')]
    public function пункт_видят_роли_со_справочниками(string $role, bool $sees): void
    {
        $this->actingAs(User::factory()->create([
            'is_admin' => true,
            'admin_role' => $role,
            'status' => 'active',
        ]));

        $response = $this->get('/admin');

        $sees
            ? $response->assertSee(self::LINK, false)
            : $response->assertDontSee(self::LINK, false);
    }
}
