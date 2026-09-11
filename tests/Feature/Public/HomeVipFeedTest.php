<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Company;
use App\Models\Listing;
use App\Models\Plan;
use App\Models\Subscription;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Лента товаров на главной — витрина тарифа VIP.
 *
 * Место на первом экране продаётся вместе с тарифом, поэтому в ленту
 * попадают только объявления компаний с действующей подпиской VIP.
 * Остальные видны в каталоге, куда ведёт ссылка «Все товары».
 */
class HomeVipFeedTest extends TestCase
{
    use RefreshDatabase;

    private function company(string $name, ?string $planCode, array $subscription = []): Company
    {
        $company = Company::factory()->create(['name' => $name, 'status' => 'active']);

        if ($planCode !== null) {
            $plan = Plan::query()->firstOrCreate(
                ['code' => $planCode],
                ['name' => mb_strtoupper($planCode), 'price_usd' => 0, 'period_days' => 30, 'listing_days' => 30],
            );

            Subscription::query()->create([
                'company_id' => $company->id,
                'plan_id' => $plan->id,
                'status' => 'active',
                'started_at' => now()->subMonth(),
                'ends_at' => now()->addMonth(),
                ...$subscription,
            ]);
        }

        return $company;
    }

    private function listing(Company $company, string $title): Listing
    {
        $listing = Listing::factory()->create([
            'company_id' => $company->id,
            'title' => $title,
            'type' => Listing::TYPE_SUPPLY,
            'status' => Listing::STATUS_ACTIVE,
            'published_at' => now()->subDay(),
            'expires_at' => now()->addDays(30),
        ]);

        if (blank($listing->slug)) {
            $listing->forceFill(['slug' => Listing::makeSlug($listing->title, $listing->id)])->save();
        }

        return $listing;
    }

    /** @return list<string> */
    private function feedTitles(): array
    {
        $page = $this->get('/')->assertOk()->viewData('page');

        return array_column($page['props']['latest'], 'title');
    }

    #[Test]
    public function лента_главной_показывает_только_товары_vip(): void
    {
        $this->listing($this->company('VIP-поставщик', Plan::VIP), 'Цемент от VIP');
        $this->listing($this->company('Бесплатный поставщик', null), 'Цемент без тарифа');
        $this->listing($this->company('Премиум-поставщик', 'premium'), 'Цемент от Premium');

        $this->assertSame(['Цемент от VIP'], $this->feedTitles());
    }

    #[Test]
    public function истёкшая_подписка_vip_из_ленты_выпадает(): void
    {
        $expired = $this->company('Бывший VIP', Plan::VIP, [
            'started_at' => now()->subYear(),
            'ends_at' => now()->subDay(),
        ]);

        $this->listing($expired, 'Цемент вчерашнего VIP');

        $this->assertSame([], $this->feedTitles());
    }

    #[Test]
    public function бессрочная_подписка_vip_в_ленте_остаётся(): void
    {
        $forever = $this->company('Вечный VIP', Plan::VIP, ['ends_at' => null]);

        $this->listing($forever, 'Цемент бессрочного VIP');

        $this->assertSame(['Цемент бессрочного VIP'], $this->feedTitles());
    }

    #[Test]
    public function главная_открывается_когда_vip_нет(): void
    {
        $this->listing($this->company('Обычный поставщик', null), 'Цемент без тарифа');

        $this->get('/')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page->component('Home')->where('latest', []));
    }
}
