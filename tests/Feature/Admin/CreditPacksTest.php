<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Exceptions\RecordIsReferenced;
use App\Models\Company;
use App\Models\CreditPack;
use App\Models\User;
use App\Services\OrderService;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Пакеты контактов.
 *
 * Раздел с этапа 2 переноса работает на Python
 * (python/savdex/billing/admin.py, проверки —
 * python/tests/test_credit_packs_admin.py). Здесь — пункт меню и то,
 * что обязано держаться в модели, кто бы ни правил.
 */
class CreditPacksTest extends TestCase
{
    use RefreshDatabase;

    private const LINK = '/admin/python?next=/py/admin/billing/creditpack/';

    /** @return array<string, array{string, bool}> */
    public static function роли(): array
    {
        return [
            'суперадмин' => [AdminAccess::SUPERADMIN, true],
            'финансы' => [AdminAccess::FINANCE, true],
            'администратор' => [AdminAccess::ADMIN, false],
            'продажи' => [AdminAccess::SALES, false],
            'контент' => [AdminAccess::CONTENT_MANAGER, false],
        ];
    }

    #[Test]
    #[DataProvider('роли')]
    public function пункт_видят_те_же_роли(string $role, bool $sees): void
    {
        $this->actingAs(User::factory()->create([
            'is_admin' => true, 'admin_role' => $role, 'status' => 'active',
        ]));

        $response = $this->get('/admin');

        $sees
            ? $response->assertSee(self::LINK, false)
            : $response->assertDontSee(self::LINK, false);
    }

    /**
     * Пакет со счётом не удаляется.
     *
     * Кредиты начисляются по пакету: удалённый пакет обнулился бы у
     * счёта, и оплаченный после этого счёт не начислил бы ни одного
     * кредита — деньги пришли, контактов нет.
     */
    #[Test]
    public function пакет_со_счётом_не_удаляется(): void
    {
        $pack = CreditPack::where('code', 'pack_30')->firstOrFail();
        $user = User::factory()->create();
        $company = Company::factory()->create();
        app(OrderService::class)->orderCredits($company, $pack, $user);

        try {
            $pack->delete();
            $this->fail('пакет со счётом удалился');
        } catch (RecordIsReferenced $e) {
            $this->assertSame(['счета' => 1], $e->references);
        }

        $this->assertModelExists($pack);
    }

    #[Test]
    public function пакет_без_счетов_удаляется(): void
    {
        $pack = CreditPack::create([
            'code' => 'pack_trial', 'name' => 'Пробный', 'credits' => 1, 'price_usd' => 1,
        ]);

        $pack->delete();

        $this->assertModelMissing($pack);
    }
}
