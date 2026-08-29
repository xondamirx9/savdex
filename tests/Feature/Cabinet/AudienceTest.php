<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\AudienceView;
use App\Models\Company;
use App\Models\Listing;
use App\Models\Plan;
use App\Models\Subscription;
use App\Models\User;
use App\Services\SubscriptionService;
use Database\Seeders\PlanSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * «Кто мной интересуется»: просмотры объявлений и визитки с указанием
 * зрителя.
 *
 * Цена ошибки двоякая: недописать зрителя — раздел пуст и бесполезен;
 * переписать лишнего (гостя, самого владельца) — владелец увидит
 * «интерес», которого не было, и разочаруется в данных. Имена зрителей —
 * платная часть тарифа, и их утечка на младший тариф обесценит Business.
 */
class AudienceTest extends TestCase
{
    use RefreshDatabase;

    private Company $owner;

    private User $ownerUser;

    private Company $visitor;

    private User $visitorUser;

    private Listing $listing;

    protected function setUp(): void
    {
        parent::setUp();

        $this->seed(PlanSeeder::class);

        $this->owner = Company::factory()->create();
        $this->ownerUser = User::factory()->for($this->owner)->create(['email_verified_at' => now()]);

        $this->visitor = Company::factory()->create();
        $this->visitorUser = User::factory()->for($this->visitor)->create(['email_verified_at' => now()]);

        $this->listing = Listing::factory()->create([
            'company_id' => $this->owner->id,
            'status' => Listing::STATUS_ACTIVE,
            'published_at' => now()->subDay(),
            'title' => 'Цемент М400 навалом, отгрузка с завода',
        ]);
    }

    /** Владельцу — тариф, на котором имена интересующихся видны. */
    private function grantBusiness(): void
    {
        app(SubscriptionService::class)->assign(
            $this->owner,
            Plan::where('code', 'business')->firstOrFail(),
            days: 30,
            source: Subscription::SOURCE_MANUAL,
            reason: 'Тест',
        );
    }

    // ── Запись просмотров ────────────────────────────────────

    #[Test]
    public function просмотр_объявления_оставляет_след_зрителя(): void
    {
        $this->actingAs($this->visitorUser)->get("/listing/{$this->listing->slug}")->assertOk();

        $view = AudienceView::firstOrFail();

        $this->assertSame($this->owner->id, $view->target_company_id);
        $this->assertSame($this->visitor->id, $view->viewer_company_id);
        $this->assertSame($this->listing->id, $view->listing_id);
    }

    #[Test]
    public function просмотр_визитки_оставляет_след_без_объявления(): void
    {
        $this->actingAs($this->visitorUser)->get("/company/{$this->owner->slug}")->assertOk();

        $view = AudienceView::firstOrFail();

        $this->assertSame($this->owner->id, $view->target_company_id);
        $this->assertSame($this->visitor->id, $view->viewer_company_id);
        $this->assertNull($view->listing_id);
    }

    /** Гость — не компания: записывать некого. */
    #[Test]
    public function гость_следа_не_оставляет(): void
    {
        $this->get("/listing/{$this->listing->slug}")->assertOk();
        $this->get("/company/{$this->owner->slug}")->assertOk();

        $this->assertSame(0, AudienceView::count());
    }

    /** Свои просмотры — не аудитория: владелец правит карточку, а не интересуется собой. */
    #[Test]
    public function владелец_своих_страниц_не_записывается(): void
    {
        $this->actingAs($this->ownerUser)->get("/listing/{$this->listing->slug}")->assertOk();
        $this->actingAs($this->ownerUser)->get("/company/{$this->owner->slug}")->assertOk();

        $this->assertSame(0, AudienceView::count());
    }

    /**
     * Накрутка сменой сессии: сессионный кэш дедупликации обходится
     * сбросом куки, поэтому повторы отсеиваются ещё и по базе.
     * Тестовый клиент как раз заводит новую сессию на каждый запрос.
     */
    #[Test]
    public function повторный_просмотр_из_новой_сессии_не_дублируется(): void
    {
        $this->actingAs($this->visitorUser)->get("/listing/{$this->listing->slug}");
        $this->actingAs($this->visitorUser)->get("/listing/{$this->listing->slug}");
        $this->actingAs($this->visitorUser)->get("/company/{$this->owner->slug}");
        $this->actingAs($this->visitorUser)->get("/company/{$this->owner->slug}");

        $this->assertSame(2, AudienceView::count());
    }

    // ── Раздел кабинета ──────────────────────────────────────

    #[Test]
    public function на_business_видно_кто_смотрел_и_что_именно(): void
    {
        $this->grantBusiness();

        $this->actingAs($this->visitorUser)->get("/listing/{$this->listing->slug}");
        $this->actingAs($this->visitorUser)->get("/company/{$this->owner->slug}");

        $this->actingAs($this->ownerUser)->get('/cabinet/incoming')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->component('cabinet/Incoming')
                ->where('sees_names', true)
                ->has('viewers', 1)
                ->where('viewers.0.name', $this->visitor->name)
                ->where('viewers.0.views', 2)
                ->where('viewers.0.looked', 'Цемент М400 навалом, отгрузка с завода · визитка компании'));
    }

    /**
     * На бесплатном тарифе факт интереса виден, имя — нет. Рейтинг
     * и уровень проверки тоже прячутся: по точному рейтингу компания
     * однозначно находится в открытом каталоге и без имени.
     */
    #[Test]
    public function на_бесплатном_тарифе_имя_зрителя_скрыто(): void
    {
        $this->visitor->forceFill(['rating' => 4.73, 'verification_level' => 2])->save();

        $this->actingAs($this->visitorUser)->get("/listing/{$this->listing->slug}");

        $this->actingAs($this->ownerUser)->get('/cabinet/incoming')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('sees_names', false)
                ->has('viewers', 1)
                ->where('viewers.0.name', null)
                ->where('viewers.0.slug', null)
                ->where('viewers.0.rating', 0)
                ->where('viewers.0.verified', 0));
    }

    /**
     * Снятое с публикации объявление остаётся в истории под своим
     * названием: просмотр был, когда оно существовало. Превращаться
     * в «визитку компании» или пустую подпись оно не должно.
     */
    #[Test]
    public function удалённое_объявление_остаётся_под_своим_названием(): void
    {
        $this->grantBusiness();

        $this->actingAs($this->visitorUser)->get("/listing/{$this->listing->slug}");

        $this->listing->delete();

        $this->actingAs($this->ownerUser)->get('/cabinet/incoming')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('viewers', 1)
                ->where('viewers.0.looked', 'Цемент М400 навалом, отгрузка с завода'));
    }
}
