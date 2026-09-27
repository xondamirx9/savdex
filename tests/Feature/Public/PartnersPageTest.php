<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Filament\Resources\Companies\Pages\ListCompanies;
use App\Models\Company;
use App\Models\User;
use Filament\Actions\Testing\TestAction;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Страница «Партнёры»: генеральные партнёры и партнёры.
 *
 * Состав назначает администратор — страница сама никого не отбирает,
 * в том числе по уровню проверки.
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
    public function партнёры_раскладываются_по_вкладкам(): void
    {
        $general = $this->company(Company::PARTNER_GENERAL);
        $partner = $this->company(Company::PARTNER_REGULAR);
        // Проверенная, но не партнёр — на странице её нет
        $this->company(null, ['verification_level' => Company::VERIFICATION_EXTENDED]);

        $this->get('/partners')->assertInertia(fn (AssertableInertia $page) => $page
            ->component('Partners')
            ->has('general', 1)
            ->where('general.0.slug', $general->slug)
            ->has('partners', 1)
            ->where('partners.0.slug', $partner->slug));
    }

    #[Test]
    public function порядок_задаёт_администратор_а_заблокированных_нет(): void
    {
        $second = $this->company(Company::PARTNER_REGULAR, ['rating' => 5]);
        $second->forceFill(['partner_sort' => 2])->save();
        $first = $this->company(Company::PARTNER_REGULAR, ['rating' => 1]);
        $first->forceFill(['partner_sort' => 1])->save();
        $this->company(Company::PARTNER_REGULAR, ['status' => 'blocked']);

        $this->get('/partners')->assertInertia(fn (AssertableInertia $page) => $page
            ->has('partners', 2)
            ->where('partners.0.slug', $first->slug)
            ->where('partners.1.slug', $second->slug));
    }

    /** Назначить и снять партнёра администратор может в любой момент. */
    #[Test]
    public function администратор_назначает_и_снимает_партнёра(): void
    {
        $this->actingAs(User::factory()->create([
            'is_admin' => true,
            'admin_role' => User::ADMIN_SUPERADMIN,
            'status' => 'active',
        ]));

        $company = Company::factory()->create();

        Livewire::test(ListCompanies::class)
            ->callAction(TestAction::make('partner')->table($company), ['tier' => Company::PARTNER_GENERAL, 'sort' => 3]);

        $this->assertSame(Company::PARTNER_GENERAL, $company->fresh()->partner_tier);
        $this->assertSame(3, (int) $company->fresh()->partner_sort);

        Livewire::test(ListCompanies::class)
            ->callAction(TestAction::make('partner')->table($company), ['tier' => 'none', 'sort' => 0]);

        $this->assertNull($company->fresh()->partner_tier);
    }
}
