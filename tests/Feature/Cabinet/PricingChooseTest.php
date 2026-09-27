<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\Company;
use App\Models\Plan;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * «Выбрать» на странице тарифов ведёт к оплате выбранного тарифа.
 *
 * Раньше кнопка у всех вела на регистрацию — и у тех, кто уже вошёл:
 * человек с аккаунтом попадал на форму регистрации, а новичок после
 * регистрации оказывался в кабинете и искал тариф заново.
 */
class PricingChooseTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();

        foreach (['free' => 0, 'business' => 39] as $code => $price) {
            Plan::create([
                'code' => $code,
                'name' => ucfirst($code),
                'price_usd' => $price,
                'listings_limit' => 50,
                'contacts_limit' => 50,
                'promo_units' => 0,
                'is_active' => true,
            ]);
        }
    }

    #[Test]
    public function регистрация_с_тарифом_возвращает_на_оплату_после_подтверждения_почты(): void
    {
        $this->get('/register?plan=business')->assertOk();

        $user = User::factory()->create(['email_verified_at' => now()]);

        $this->actingAs($user)
            ->get('/verify-email')
            ->assertRedirect(url('/cabinet/billing?plan=business'));
    }

    #[Test]
    public function бесплатный_и_выдуманный_тариф_не_запоминаются(): void
    {
        foreach (['free', 'nonexistent', '../admin'] as $code) {
            $this->get('/register?plan='.urlencode($code))->assertOk()->assertSessionMissing('url.intended');
        }
    }

    #[Test]
    public function кабинет_получает_выбранный_тариф(): void
    {
        $company = Company::factory()->create();
        $user = User::factory()->create(['company_id' => $company->id]);

        $this->actingAs($user)
            ->get('/cabinet/billing?plan=business')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('selected', 'business')
                ->where('plans.1.code', 'business')
                ->where('plans.1.orderable', true));
    }

    /** Переход по ссылке счёт не выставляет — только POST из окна оплаты. */
    #[Test]
    public function ссылка_с_тарифом_не_создаёт_счёт(): void
    {
        $company = Company::factory()->create();
        $user = User::factory()->create(['company_id' => $company->id]);

        $this->actingAs($user)->get('/cabinet/billing?plan=business');

        $this->assertDatabaseCount('payments', 0);
    }
}
