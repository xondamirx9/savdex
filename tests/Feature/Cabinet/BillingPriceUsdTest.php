<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\Company;
use App\Models\CreditPack;
use App\Models\Plan;
use App\Models\User;
use App\Support\CurrencyRate;
use App\Support\PriceDisplay;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Цена в долларах на странице оплаты.
 *
 * Тарифы и пакеты задаются в долларах, а сумовая цена выводится из
 * них по курсу ЦБ. В кассе кабинета стояли одни сумы: покупатель
 * с валютным бюджетом считал курс сам, хотя на витрине тарифов обе
 * цифры показаны с самого начала.
 */
class BillingPriceUsdTest extends TestCase
{
    use RefreshDatabase;

    private User $user;

    protected function setUp(): void
    {
        parent::setUp();

        Plan::create([
            'code' => 'free', 'name' => 'Free', 'price_usd' => 0,
            'listings_limit' => 4, 'contacts_limit' => 3, 'promo_units' => 0, 'is_active' => true,
        ]);

        $this->user = User::factory()->for(Company::factory())->create(['email_verified_at' => now()]);
    }

    private function rate(): float
    {
        return app(CurrencyRate::class)->usd();
    }

    #[Test]
    public function тариф_и_пакет_приходят_с_долларовой_ценой(): void
    {
        Plan::create([
            'code' => 'business', 'name' => 'Business', 'price_usd' => 79,
            'listings_limit' => 20, 'contacts_limit' => 20, 'promo_units' => 0, 'is_active' => true,
        ]);

        CreditPack::create([
            'code' => 'pack10', 'name' => '10 контактов', 'credits' => 10,
            'price_usd' => 9, 'sort' => 1, 'is_active' => true,
        ]);

        $this->actingAs($this->user)
            ->get('/cabinet/billing')
            ->assertInertia(fn (AssertableInertia $page) => $page
                // Из JSON число приходит как int, когда дробной части
                // нет, — сравнение приводит обе стороны к float
                ->where('plans', fn ($plans) => (float) collect($plans)->firstWhere('code', 'business')['price_usd'] === 79.0)
                ->where('packs', fn ($packs) => (float) collect($packs)->first()['price_usd'] === 9.0));
    }

    /**
     * Зафиксированная сумовая цена перебивает долларовую.
     *
     * Иначе на карточке стояли бы две цены из разных расчётов:
     * сумы — назначенные вручную, доллары — от прежней цены.
     */
    #[Test]
    public function при_зафиксированной_цене_доллары_считаются_от_сумов(): void
    {
        $plan = Plan::create([
            'code' => 'premium', 'name' => 'Premium', 'price_usd' => 149, 'price_uzs' => 1_771_000,
            'listings_limit' => 50, 'contacts_limit' => 50, 'promo_units' => 0, 'is_active' => true,
        ]);

        // Округление то же, что у пересчитанных цен на витрине:
        // три значащих цифры (PriceDisplay::round)
        $expected = PriceDisplay::round(1_771_000 / $this->rate());

        $this->assertSame($expected, $plan->priceUsd($this->rate()));
        $this->assertNotSame(149.0, $plan->priceUsd($this->rate()));
    }

    /** Бесплатный тариф долларовой строки не получает — её нечем заполнить. */
    #[Test]
    public function бесплатный_тариф_стоит_ноль_долларов(): void
    {
        $this->assertSame(0.0, Plan::where('code', 'free')->sole()->priceUsd($this->rate()));
    }
}
