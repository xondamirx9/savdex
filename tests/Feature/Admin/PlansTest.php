<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Exceptions\RecordIsReferenced;
use App\Models\Company;
use App\Models\Plan;
use App\Models\User;
use App\Services\OrderService;
use App\Support\AdminAccess;
use Database\Seeders\PlanSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Тарифы: кто задаёт цены и что держит тариф от удаления.
 *
 * Раздел с этапа 2 переноса работает на Python
 * (python/savdex/billing/admin.py, проверки —
 * python/tests/test_plans_admin.py). Цены и лимиты задаёт админка
 * (решение заказчика) — сидер их больше не возвращает.
 */
class PlansTest extends TestCase
{
    use RefreshDatabase;

    private const LINK = '/admin/python?next=/py/admin/billing/plan/';

    /**
     * Деплой не откатывает правки тарифов.
     *
     * PlanSeeder гоняется на каждом деплое и раньше возвращал тарифам
     * цену, лимиты и название из кода: правка в админке жила до
     * следующего деплоя.
     */
    #[Test]
    public function сидер_не_откатывает_правки_тарифов(): void
    {
        $this->seed(PlanSeeder::class);

        $business = Plan::where('code', 'business')->firstOrFail();
        $business->update(['price_usd' => 77, 'listings_limit' => 999, 'name' => 'Бизнес+']);
        $count = Plan::count();

        $this->seed(PlanSeeder::class);

        $business->refresh();
        $this->assertSame('77.00', $business->price_usd);
        $this->assertSame(999, $business->listings_limit);
        $this->assertSame('Бизнес+', $business->name);
        $this->assertSame($count, Plan::count(), 'дублей нет');
    }

    /** Удалённый тариф сидер заводит снова — на свежей базе все пять на месте. */
    #[Test]
    public function сидер_заводит_недостающие(): void
    {
        $this->seed(PlanSeeder::class);

        $this->assertSame(
            ['business', 'flash', 'free', 'premium', 'vip'],
            Plan::query()->orderBy('code')->pluck('code')->all(),
        );
    }

    /** На free и vip опирается код: без них ломаются лимиты и лента главной. */
    #[Test]
    public function free_и_vip_не_удаляются(): void
    {
        $this->seed(PlanSeeder::class);

        foreach ([Plan::FREE, Plan::VIP] as $code) {
            try {
                Plan::where('code', $code)->firstOrFail()->delete();
                $this->fail("тариф {$code} удалился");
            } catch (RecordIsReferenced $e) {
                $this->assertArrayHasKey('код площадки', $e->references);
            }
        }
    }

    /** Счёт на тариф держит его: иначе у счёта обнулился бы тариф. */
    #[Test]
    public function тариф_со_счётом_не_удаляется(): void
    {
        $this->seed(PlanSeeder::class);
        $flash = Plan::where('code', 'flash')->firstOrFail();
        $user = User::factory()->create();
        app(OrderService::class)->orderPlan(Company::factory()->create(), $flash, $user);

        try {
            $flash->delete();
            $this->fail('тариф со счётом удалился');
        } catch (RecordIsReferenced $e) {
            $this->assertSame(['счета' => 1], $e->references);
        }
    }

    #[Test]
    public function пустой_тариф_удаляется(): void
    {
        $plan = Plan::create(['code' => 'trial', 'name' => 'Пробный', 'price_usd' => 1]);

        $plan->delete();

        $this->assertModelMissing($plan);
    }

    #[Test]
    public function пункт_тарифов_видят_суперадмин_и_финансы(): void
    {
        foreach ([AdminAccess::SUPERADMIN => true, AdminAccess::FINANCE => true, AdminAccess::ADMIN => false, AdminAccess::SALES => false] as $role => $sees) {
            $this->actingAs(User::factory()->create(['is_admin' => true, 'admin_role' => $role, 'status' => 'active']));

            $response = $this->get('/admin');
            $sees ? $response->assertSee(self::LINK, false) : $response->assertDontSee(self::LINK, false);
        }
    }
}
