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
 * Пункты меню «Категории» и «Типы компаний».
 *
 * Разделы с этапа 2 переноса работают на Python
 * (python/savdex/catalogs/admin.py, проверки —
 * python/tests/test_categories_admin.py и test_company_types_admin.py).
 * Из Filament туда ведут пункты меню через пропуск, и видеть их должны
 * те же роли, что видели прежние разделы, — у кого есть справочники.
 */
class CatalogsMenuTest extends TestCase
{
    use RefreshDatabase;

    private const LINKS = [
        '/admin/python?next=/py/admin/catalogs/category/',
        '/admin/python?next=/py/admin/catalogs/companytype/',
    ];

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
    public function пункты_видят_роли_со_справочниками(string $role, bool $sees): void
    {
        $this->actingAs(User::factory()->create([
            'is_admin' => true,
            'admin_role' => $role,
            'status' => 'active',
        ]));

        $response = $this->get('/admin');

        foreach (self::LINKS as $link) {
            $sees
                ? $response->assertSee($link, false)
                : $response->assertDontSee($link, false);
        }
    }
}
