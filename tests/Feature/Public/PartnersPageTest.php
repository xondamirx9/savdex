<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Company;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Раздел «Партнёры»: три вида партнёрства — генеральные партнёры,
 * партнёры и мультипартнёры.
 *
 * Страница раздела показывает только виды со счётчиками, списки —
 * на отдельных страницах. Состав назначает администратор — в разделе
 * «Компании» на Python (python/tests/test_companies_admin.py).
 */
class PartnersPageTest extends TestCase
{
    use RefreshDatabase;

    private function company(?string $tier, array $overrides = []): Company
    {
        $company = Company::factory()->create($overrides);
        $company->forceFill(['partner_tier' => $tier])->save();

        return $company;
    }

    #[Test]
    public function раздел_показывает_три_вида_со_счётчиками(): void
    {
        $this->company(Company::PARTNER_GENERAL);
        $this->company(Company::PARTNER_REGULAR);
        $this->company(Company::PARTNER_REGULAR);
        $this->company(Company::PARTNER_MULTI);
        // Не партнёр и заблокированный партнёр не считаются
        $this->company(null);
        $this->company(Company::PARTNER_MULTI, ['status' => 'blocked']);

        $this->get('/partners')->assertInertia(fn (AssertableInertia $page) => $page
            ->component('Partners')
            ->where('tiers', [
                ['slug' => 'general', 'count' => 1],
                ['slug' => 'regular', 'count' => 2],
                ['slug' => 'multi', 'count' => 1],
            ])
            ->missing('partners'));
    }

    #[Test]
    public function у_каждого_вида_своя_страница(): void
    {
        $general = $this->company(Company::PARTNER_GENERAL);
        $partner = $this->company(Company::PARTNER_REGULAR);
        $multi = $this->company(Company::PARTNER_MULTI);

        foreach (['general' => $general, 'regular' => $partner, 'multi' => $multi] as $slug => $company) {
            $this->get('/partners/'.$slug)->assertOk()->assertInertia(fn (AssertableInertia $page) => $page
                ->component('PartnersTier')
                ->where('tier', $slug)
                ->has('partners', 1)
                ->where('partners.0.slug', $company->slug)
                ->has('others', 2));
        }

        $this->get('/partners/unknown')->assertNotFound();
    }

    #[Test]
    public function порядок_задаёт_администратор(): void
    {
        $second = $this->company(Company::PARTNER_REGULAR, ['rating' => 5]);
        $second->forceFill(['partner_sort' => 2])->save();
        $first = $this->company(Company::PARTNER_REGULAR, ['rating' => 1]);
        $first->forceFill(['partner_sort' => 1])->save();

        $this->get('/partners/regular')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('partners.0.slug', $first->slug)
            ->where('partners.1.slug', $second->slug));
    }
}
