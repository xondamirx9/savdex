<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\Company;
use App\Models\CompanySite;
use App\Models\Plan;
use App\Models\Subscription;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Редактор мини-сайта в кабинете.
 */
class SiteEditorTest extends TestCase
{
    use RefreshDatabase;

    private Company $company;

    private User $user;

    private const THEME = [
        'template' => 'minimal',
        'primary' => '#5b3cc4',
        'accent' => '#e11d74',
        'mode' => 'dark',
        'heading_font' => 'montserrat',
        'body_font' => 'rubik',
        'radius' => 'round',
    ];

    protected function setUp(): void
    {
        parent::setUp();

        $this->company = Company::factory()->create(['slug' => 'acme-trade']);
        $this->user = User::factory()->create(['company_id' => $this->company->id]);
    }

    private function subscribe(): void
    {
        $plan = Plan::create([
            'code' => 'business',
            'name' => 'Business',
            'price_usd' => 39,
            'listings_limit' => 50,
            'contacts_limit' => 50,
            'promo_units' => 0,
            'has_microsite' => true,
        ]);

        Subscription::create([
            'company_id' => $this->company->id,
            'plan_id' => $plan->id,
            'status' => 'active',
            'started_at' => now(),
            'ends_at' => now()->addDays(30),
        ]);
    }

    #[Test]
    public function редактор_предлагает_адрес_из_карточки(): void
    {
        $this->actingAs($this->user)
            ->get('/cabinet/site')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->component('cabinet/Site')
                ->where('available', false)
                ->where('subdomain', 'acme-trade')
                ->where('site', null)
                ->where('theme.template', 'classic'));
    }

    #[Test]
    public function без_тарифа_сохранить_нельзя(): void
    {
        $this->actingAs($this->user)
            ->patch('/cabinet/site', ['subdomain' => 'acme', 'theme' => self::THEME])
            ->assertSessionHas('error');

        $this->assertDatabaseCount('company_sites', 0);
    }

    #[Test]
    public function сохранение_меняет_черновик_а_публикация_витрину(): void
    {
        $this->subscribe();

        $this->actingAs($this->user)
            ->patch('/cabinet/site', ['subdomain' => 'acme', 'theme' => self::THEME])
            ->assertSessionHas('success');

        $site = CompanySite::firstOrFail();
        $this->assertSame(self::THEME, $site->draftTheme());
        $this->assertFalse($site->isPublished());

        $this->actingAs($this->user)->post('/cabinet/site/publish')->assertSessionHas('success');

        $site->refresh();
        $this->assertTrue($site->isLive());
        $this->assertSame(self::THEME, $site->publishedTheme());
        $this->assertFalse($site->hasUnpublishedChanges());
    }

    #[Test]
    public function адрес_проверяется(): void
    {
        $this->subscribe();

        CompanySite::create(['company_id' => Company::factory()->create()->id, 'subdomain' => 'taken']);

        foreach (['taken', 'admin', 'ab', '-acme', 'acme-', 'a.b', 'ACME'] as $bad) {
            $this->actingAs($this->user)
                ->patch('/cabinet/site', ['subdomain' => $bad, 'theme' => self::THEME])
                ->assertSessionHasErrors('subdomain');
        }

        $this->assertDatabaseMissing('company_sites', ['company_id' => $this->company->id]);
    }

    #[Test]
    public function свой_адрес_можно_сохранить_повторно(): void
    {
        $this->subscribe();

        $this->actingAs($this->user)->patch('/cabinet/site', ['subdomain' => 'acme', 'theme' => self::THEME]);
        $this->actingAs($this->user)
            ->patch('/cabinet/site', ['subdomain' => 'acme', 'theme' => [...self::THEME, 'mode' => 'light']])
            ->assertSessionHasNoErrors();

        $this->assertSame('light', CompanySite::firstOrFail()->draftTheme()['mode']);
    }

    #[Test]
    public function чужие_значения_темы_не_принимаются(): void
    {
        $this->subscribe();

        $this->actingAs($this->user)
            ->patch('/cabinet/site', [
                'subdomain' => 'acme',
                'theme' => [...self::THEME, 'primary' => 'red;}body{display:none', 'heading_font' => 'Comic Sans'],
            ])
            ->assertSessionHasErrors(['theme.primary', 'theme.heading_font']);
    }

    #[Test]
    public function предпросмотр_показывает_присланную_тему_и_закрыт_от_поиска(): void
    {
        $this->actingAs($this->user)
            ->get('/cabinet/site/preview?theme='.urlencode(json_encode(self::THEME)))
            ->assertOk()
            ->assertSee('noindex', false)
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->component('site/Show')
                ->where('preview', true)
                ->where('theme.template', 'minimal')
                ->where('vars.--ms-primary', '#5b3cc4'));
    }

    #[Test]
    public function снять_с_публикации_можно_и_без_тарифа(): void
    {
        $site = CompanySite::create(['company_id' => $this->company->id, 'subdomain' => 'acme']);
        $site->publish();

        $this->actingAs($this->user)->post('/cabinet/site/unpublish');

        $this->assertFalse($site->refresh()->isPublished());
    }
}
