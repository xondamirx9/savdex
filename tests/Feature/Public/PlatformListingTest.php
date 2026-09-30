<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\City;
use App\Models\Company;
use App\Models\CompanyContact;
use App\Models\Country;
use App\Models\Listing;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Заявки площадки: загруженные из Excel без компании лежат у служебной
 * компании (Anjir Group), а на витрине подписаны SavdEx — служебная
 * компания не продаёт и не покупает, показывать её продавцом нельзя.
 * Собственные объявления этой компании, написанные в кабинете, — обычные.
 */
class PlatformListingTest extends TestCase
{
    use RefreshDatabase;

    private Company $service;

    protected function setUp(): void
    {
        parent::setUp();

        $this->service = Company::factory()->create(['name' => 'ООО Anjir Group', 'status' => 'active']);
        CompanyContact::query()->create([
            'company_id' => $this->service->id, 'type' => 'phone', 'value' => '+998 90 111-22-33', 'is_public' => true,
        ]);
    }

    /** @param array<string, mixed> $overrides */
    private function listing(array $overrides = []): Listing
    {
        return Listing::factory()->create([
            'company_id' => $this->service->id,
            'status' => Listing::STATUS_ACTIVE,
            'published_at' => now()->subDay(),
            'expires_at' => now()->addDays(30),
            'source' => Listing::SOURCE_IMPORT,
            'type' => Listing::TYPE_DEMAND,
            ...$overrides,
        ]);
    }

    #[Test]
    public function заявка_площадки_подписана_savdex_без_контактов_компании(): void
    {
        $country = Country::query()->firstOrCreate(['code' => 'uz'], ['sort' => 0, 'is_active' => true]);
        $city = City::query()->create(['country_id' => $country->id, 'slug' => 'fergana', 'sort' => 0, 'is_active' => true]);
        $city->translations()->create(['locale' => 'ru', 'name' => 'Фергана']);
        $listing = $this->listing(['title' => 'Куплю сепаратор САД-5', 'city_id' => $city->id]);

        $this->get('/listing/'.$listing->slug)->assertInertia(fn (AssertableInertia $page) => $page
            ->component('catalog/Show')
            ->where('company.name', 'SavdEx')
            ->where('company.slug', null)
            ->where('company.platform', true)
            ->where('company.city', 'Фергана')
            ->where('contacts', [])
            ->where('unlocked', false));

        $this->get('/catalog')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('listings.data.0.company.name', 'SavdEx')
            ->where('listings.data.0.company.platform', true)
            ->where('listings.data.0.company.slug', null));
    }

    #[Test]
    public function собственное_объявление_служебной_компании_обычное(): void
    {
        $listing = $this->listing(['title' => 'Поддоны деревянные', 'source' => 'cabinet']);

        $this->get('/listing/'.$listing->slug)->assertInertia(fn (AssertableInertia $page) => $page
            ->where('company.name', 'ООО Anjir Group')
            ->where('company.platform', false)
            ->has('contacts', 1));
    }

    #[Test]
    public function на_странице_служебной_компании_заявки_площадки_не_считаются(): void
    {
        $this->listing(['title' => 'Куплю сепаратор САД-5']);
        $this->listing(['title' => 'Поддоны деревянные', 'source' => 'cabinet']);

        $this->get('/company/'.$this->service->slug)->assertInertia(fn (AssertableInertia $page) => $page
            ->where('listings_count', 1));
    }
}
