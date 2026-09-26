<?php

declare(strict_types=1);

namespace Tests\Feature\Microsite;

use App\Models\Company;
use App\Models\CompanyContact;
use App\Models\CompanySite;
use App\Models\Plan;
use App\Models\Subscription;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Мини-сайт на acme.savdex.site глазами посетителя.
 *
 * Сайт показывается, только пока выполнены все три условия: он
 * опубликован, компания не заблокирована и тариф включает мини-сайт.
 * Любое нарушение — 404, неотличимый от несуществующего адреса.
 */
class MicrositeTest extends TestCase
{
    use RefreshDatabase;

    private const HOST = 'http://acme.savdex.site';

    private Company $company;

    protected function setUp(): void
    {
        parent::setUp();

        $this->company = Company::factory()->create(['name' => 'ООО «Акме»', 'description' => 'Цемент и бетон']);
    }

    private function subscribe(bool $microsite = true): void
    {
        $plan = Plan::create([
            'code' => $microsite ? 'business' : 'flash',
            'name' => $microsite ? 'Business' : 'Flash',
            'price_usd' => 39,
            'listings_limit' => 50,
            'contacts_limit' => 50,
            'promo_units' => 0,
            'has_microsite' => $microsite,
        ]);

        Subscription::create([
            'company_id' => $this->company->id,
            'plan_id' => $plan->id,
            'status' => 'active',
            'started_at' => now(),
            'ends_at' => now()->addDays(30),
        ]);
    }

    private function site(array $theme = []): CompanySite
    {
        $site = CompanySite::create([
            'company_id' => $this->company->id,
            'subdomain' => 'acme',
            'theme' => ['primary' => '#0f6e56', 'template' => 'bold', ...$theme],
        ]);
        $site->publish();

        return $site;
    }

    #[Test]
    public function опубликованный_сайт_открывается_по_поддомену(): void
    {
        $this->subscribe();
        $this->site();

        $this->get(self::HOST.'/')
            ->assertOk()
            ->assertSee('<title inertia>ООО «Акме»</title>', false)
            ->assertSee('--ms-primary:#0f6e56', false)
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->component('site/Show')
                ->where('company.name', 'ООО «Акме»')
                ->where('theme.template', 'bold')
                ->where('preview', false));
    }

    /**
     * Контакты на мини-сайте открыты: это собственная страница
     * компании, оплаченная её тарифом, а не карточка на площадке.
     */
    #[Test]
    public function контакты_на_сайте_открыты_без_оплаты(): void
    {
        $this->subscribe();
        $this->site();

        CompanyContact::create([
            'company_id' => $this->company->id,
            'type' => 'phone',
            'value' => '+998 90 555-11-22',
            'is_public' => true,
            'is_primary' => true,
        ]);

        $this->get(self::HOST.'/')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('contacts.0.value', '+998 90 555-11-22')
                ->where('contacts.0.href', 'tel:+998905551122'));
    }

    #[Test]
    public function посетители_видят_опубликованное_а_не_черновик(): void
    {
        $this->subscribe();
        $site = $this->site();

        $site->update(['theme' => [...$site->theme, 'primary' => '#b4532a']]);

        $this->get(self::HOST.'/')
            ->assertInertia(fn (AssertableInertia $page) => $page->where('theme.primary', '#0f6e56'));
    }

    #[Test]
    public function без_тарифа_сайта_нет(): void
    {
        $this->subscribe(microsite: false);
        $this->site();

        $this->get(self::HOST.'/')->assertNotFound();
    }

    #[Test]
    public function истёкшая_подписка_выключает_сайт(): void
    {
        $this->subscribe();
        $this->site();

        Subscription::query()->update(['ends_at' => now()->subDay()]);

        $this->get(self::HOST.'/')->assertNotFound();
    }

    #[Test]
    public function заблокированная_компания_исчезает_и_со_своего_адреса(): void
    {
        $this->subscribe();
        $this->site();

        $this->company->forceFill(['status' => Company::STATUS_BLOCKED])->save();

        $this->get(self::HOST.'/')->assertNotFound();
    }

    #[Test]
    public function снятый_с_публикации_сайт_не_открывается(): void
    {
        $this->subscribe();
        $this->site()->unpublish();

        $this->get(self::HOST.'/')->assertNotFound();
    }

    #[Test]
    public function несуществующий_поддомен_404(): void
    {
        $this->get('http://nobody.savdex.site/')->assertNotFound();
    }

    /**
     * Маршруты площадки к домену не привязаны и без фильтра отвечали
     * бы и здесь: вход в кабинет SAVDEX на адресе компании — готовая
     * фишинговая страница.
     */
    #[Test]
    public function страницы_площадки_на_домене_сайтов_закрыты(): void
    {
        $this->subscribe();
        $this->site();

        foreach (['/login', '/catalog', '/cabinet', '/company/'.$this->company->slug, '/uz/catalog'] as $path) {
            $this->get(self::HOST.$path)->assertNotFound();
        }
    }

    #[Test]
    public function язык_сайта_берётся_из_префикса(): void
    {
        $this->subscribe();
        $this->site();

        $this->get(self::HOST.'/uz')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page->where('locale', 'uz'));
    }

    #[Test]
    public function корень_домена_ведёт_в_каталог_компаний(): void
    {
        $this->get('http://savdex.site/')
            ->assertRedirect(rtrim((string) config('app.url'), '/').'/companies');
    }

    #[Test]
    public function robots_мини_сайта_без_карты_площадки(): void
    {
        $this->get(self::HOST.'/robots.txt')
            ->assertOk()
            ->assertDontSee('sitemap');
    }

    #[Test]
    public function главная_площадки_не_задета(): void
    {
        $this->get('/')->assertOk()->assertInertia(fn (AssertableInertia $page) => $page->component('Home'));
    }
}
