<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\Company;
use App\Models\CompanySite;
use App\Models\CompanySiteProduct;
use App\Models\Plan;
use App\Models\Subscription;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Storage;
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
        'hero_image' => null,
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
                ->where('theme.template', 'classic')
                ->where('address.suffix', '.savdex.site'));
    }

    #[Test]
    public function без_домена_адрес_показывается_путём_площадки(): void
    {
        config(['microsite.domain' => null, 'app.url' => 'https://savdex.uz']);

        $this->actingAs($this->user)
            ->get('/cabinet/site')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('address.prefix', 'savdex.uz/s/')
                ->where('address.suffix', ''));
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

    // ── Фон первого экрана ───────────────────────────────────

    #[Test]
    public function фон_попадает_в_черновик_и_на_сайт_после_публикации(): void
    {
        Storage::fake('public');
        $this->subscribe();
        $this->actingAs($this->user)->patch('/cabinet/site', ['subdomain' => 'acme', 'theme' => self::THEME]);

        $this->actingAs($this->user)
            ->post('/cabinet/site/hero', ['hero' => UploadedFile::fake()->image('hero.jpg', 1920, 1080)])
            ->assertSessionHas('success');

        $site = CompanySite::firstOrFail();
        $path = $site->draftTheme()['hero_image'];

        $this->assertMatchesRegularExpression('#^sites/'.$this->company->id.'/#', (string) $path);
        Storage::disk('public')->assertExists((string) $path);
        $this->assertNull($site->publishedTheme()['hero_image']);

        $site->publish();
        $this->assertSame($path, $site->refresh()->publishedTheme()['hero_image']);
    }

    /** Фон нельзя подставить через форму оформления — только загрузкой. */
    #[Test]
    public function фон_из_формы_не_принимается(): void
    {
        $this->subscribe();

        $this->actingAs($this->user)->patch('/cabinet/site', [
            'subdomain' => 'acme',
            'theme' => [...self::THEME, 'hero_image' => 'sites/999/чужой.jpg'],
        ]);

        $this->assertNull(CompanySite::firstOrFail()->draftTheme()['hero_image']);
    }

    #[Test]
    public function замена_фона_удаляет_прежний_файл_если_он_не_на_сайте(): void
    {
        Storage::fake('public');
        $this->subscribe();
        $this->actingAs($this->user)->patch('/cabinet/site', ['subdomain' => 'acme', 'theme' => self::THEME]);

        $this->actingAs($this->user)->post('/cabinet/site/hero', ['hero' => UploadedFile::fake()->image('a.jpg', 800, 400)]);
        $first = CompanySite::firstOrFail()->draftTheme()['hero_image'];

        $this->actingAs($this->user)->post('/cabinet/site/hero', ['hero' => UploadedFile::fake()->image('b.jpg', 800, 400)]);

        Storage::disk('public')->assertMissing((string) $first);
    }

    // ── Товары сайта ─────────────────────────────────────────

    #[Test]
    public function товар_заводится_с_фото_и_виден_в_редакторе(): void
    {
        Storage::fake('public');
        $this->subscribe();

        $this->actingAs($this->user)
            ->post('/cabinet/site/products', [
                'title' => 'Цемент М500',
                'price' => '850000',
                'currency' => 'UZS',
                'unit' => 'т',
                'image' => UploadedFile::fake()->image('p.jpg', 800, 800),
            ])
            ->assertSessionHas('success');

        $product = CompanySiteProduct::firstOrFail();
        $this->assertSame($this->company->id, $product->company_id);
        Storage::disk('public')->assertExists((string) $product->thumb_path);

        $this->actingAs($this->user)
            ->get('/cabinet/site')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('products.0.title', 'Цемент М500')
                ->where('products.0.price', 850000));
    }

    #[Test]
    public function без_тарифа_товар_не_заводится(): void
    {
        $this->actingAs($this->user)
            ->post('/cabinet/site/products', ['title' => 'Цемент', 'currency' => 'UZS'])
            ->assertSessionHas('error');

        $this->assertDatabaseCount('company_site_products', 0);
    }

    #[Test]
    public function чужой_товар_не_изменить_и_не_удалить(): void
    {
        $this->subscribe();
        $other = CompanySiteProduct::create([
            'company_id' => Company::factory()->create()->id,
            'title' => 'Чужой',
            'currency' => 'UZS',
        ]);

        $this->actingAs($this->user)
            ->post("/cabinet/site/products/{$other->id}", ['title' => 'Моё', 'currency' => 'UZS'])
            ->assertNotFound();
        $this->actingAs($this->user)->delete("/cabinet/site/products/{$other->id}")->assertNotFound();

        $this->assertSame('Чужой', $other->refresh()->title);
    }
}
