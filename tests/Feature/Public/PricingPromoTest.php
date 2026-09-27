<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Plan;
use App\Models\PromoCode;
use App\Services\OrderService;
use App\Support\CurrencyRate;
use Database\Seeders\PlanSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Промокод на странице тарифов.
 *
 * Посетитель вводит код и видит свою цену на карточке тарифа, на
 * который код выпущен. Код при этом не гасится — гасит его активация
 * в кабинете, и цена там обязана совпасть с показанной здесь.
 */
class PricingPromoTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();

        $this->seed(PlanSeeder::class);
    }

    private function code(array $overrides = []): PromoCode
    {
        $promo = new PromoCode;
        $promo->forceFill(array_merge([
            'code' => 'SVDX-TEST2026',
            'plan_id' => Plan::where('code', 'premium')->value('id'),
            'days' => 0,
            'discount_percent' => 30,
            'is_active' => true,
        ], $overrides))->save();

        return $promo;
    }

    #[Test]
    public function скидочный_код_меняет_цену_только_своего_тарифа(): void
    {
        $promo = $this->code();
        $premium = Plan::where('code', 'premium')->firstOrFail();
        $expectedUzs = OrderService::discounted($premium->priceUzs(app(CurrencyRate::class)->usd()), 30);

        $this->get('/pricing?promo=svdx-test2026')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('promo.code', 'SVDX-TEST2026')
                ->where('promo.plan_code', 'premium')
                ->where('promo.discount_percent', 30)
                ->where('promoError', null)
                ->where('plans', fn ($plans) => collect($plans)->every(
                    fn ($p) => $p['code'] === 'premium'
                        ? $p['promo_price']['price_uzs'] === $expectedUzs
                            && abs($p['promo_price']['price_usd'] - round((float) $premium->price_usd * 0.7, 2)) < 0.001
                        : $p['promo_price'] === null
                )));

        // Проверка на витрине код не гасит
        $this->assertNull($promo->fresh()->used_at);
    }

    #[Test]
    public function код_на_бесплатный_период_показывает_ноль_и_срок(): void
    {
        $this->code(['discount_percent' => null, 'days' => 30]);

        $this->get('/pricing?promo=SVDX-TEST2026')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('promo.days', 30)
                ->where('promo.discount_percent', null)
                ->where('plans', fn ($plans) => collect($plans)->firstWhere('code', 'premium')['promo_price']['price_uzs'] === 0));
    }

    #[Test]
    public function неверный_погашенный_или_просроченный_код_объясняется(): void
    {
        $this->get('/pricing?promo=NOPE')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('promo', null)
                ->where('promoError', __('ui.messages.promo_code.unknown')));

        $this->code(['used_at' => now()]);

        $this->get('/pricing?promo=SVDX-TEST2026')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('promoError', __('ui.messages.promo_code.used')));

        PromoCode::query()->delete();
        $this->code(['expires_at' => now()->subDay()]);

        $this->get('/pricing?promo=SVDX-TEST2026')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('promoError', __('ui.messages.promo_code.expired')));
    }

    #[Test]
    public function без_кода_цены_обычные(): void
    {
        $this->get('/pricing')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('promo', null)
                ->where('promoError', null)
                ->where('plans', fn ($plans) => collect($plans)->every(fn ($p) => $p['promo_price'] === null)));
    }

    /** Проверка отвечает «такого кода нет» — без предела по ней перебирали бы коды. */
    #[Test]
    public function перебор_кодов_ограничен(): void
    {
        for ($i = 0; $i < 10; $i++) {
            $this->get('/pricing?promo=WRONG'.$i);
        }

        $this->code();

        $this->get('/pricing?promo=SVDX-TEST2026')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('promo', null)
                ->where('promoError', __('ui.pricing.promo_throttled')));
    }
}
