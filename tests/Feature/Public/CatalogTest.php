<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Category;
use App\Models\Company;
use App\Models\CompanyContact;
use App\Models\ContactUnlock;
use App\Models\Listing;
use App\Models\ListingStat;
use App\Models\Promotion;
use App\Models\PromotionType;
use App\Models\SearchHit;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Публичный каталог объявлений — витрина площадки.
 *
 * До этого `/catalog` был статической заглушкой с текстом внутреннего
 * плана работ: объявления создавались и публиковались, но покупателю
 * их негде было смотреть, и платить было не за что.
 */
class CatalogTest extends TestCase
{
    use RefreshDatabase;

    private Company $company;

    protected function setUp(): void
    {
        parent::setUp();

        $this->company = Company::factory()->create([
            'name' => 'ООО «Стройбаза»',
            'status' => 'active',
            'verification_level' => 2,
        ]);
    }

    private function listing(array $overrides = []): Listing
    {
        $listing = Listing::factory()->create([
            'company_id' => $this->company->id,
            'status' => Listing::STATUS_ACTIVE,
            'published_at' => now()->subDay(),
            'expires_at' => now()->addDays(30),
            'impressions_count' => 0,
            'views_count' => 0,
            ...$overrides,
        ]);

        if (blank($listing->slug)) {
            $listing->forceFill(['slug' => Listing::makeSlug($listing->title, $listing->id)])->save();
        }

        return $listing;
    }

    /** Процент доверия на карточке — заполненность профиля поставщика. */
    #[Test]
    public function карточка_несёт_процент_доверия_компании(): void
    {
        $this->listing(['title' => 'Цемент М400 навалом']);

        $this->get('/catalog')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('listings.data.0.company.trust', $this->company->fresh()->profileCompleteness()),
            );
    }

    #[Test]
    public function каталог_показывает_только_активные_объявления(): void
    {
        $this->listing(['title' => 'Цемент М400 навалом']);
        $this->listing(['title' => 'Черновик', 'status' => Listing::STATUS_DRAFT]);
        $this->listing(['title' => 'Истёкшее', 'status' => Listing::STATUS_EXPIRED]);

        $this->get('/catalog')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->component('catalog/Index')
                ->has('listings.data', 1)
                ->where('listings.data.0.title', 'Цемент М400 навалом'),
            );
    }

    /**
     * Объявления заблокированной компании не должны висеть в выдаче:
     * блокировка теряет смысл, если товар продолжает продаваться.
     */
    #[Test]
    public function объявления_заблокированной_компании_скрыты(): void
    {
        $blocked = Company::factory()->create(['status' => 'blocked']);

        Listing::factory()->create([
            'company_id' => $blocked->id,
            'status' => Listing::STATUS_ACTIVE,
            'published_at' => now(),
        ]);

        $this->get('/catalog')
            ->assertInertia(fn (AssertableInertia $page) => $page->has('listings.data', 0));
    }

    #[Test]
    public function поиск_находит_по_заголовку_и_описанию(): void
    {
        $this->listing(['title' => 'Цемент М400 навалом', 'description' => 'Отгрузка с завода']);
        $this->listing(['title' => 'Щебень фракция 5-20', 'description' => 'Гранитный карьер']);

        $this->get('/catalog?q=цемент')
            ->assertInertia(fn (AssertableInertia $page) => $page->has('listings.data', 1));

        // Поиск по описанию, а не только по заголовку
        $this->get('/catalog?q=карьер')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('listings.data', 1)
                ->where('listings.data.0.title', 'Щебень фракция 5-20'),
            );
    }

    /** Регистр не должен влиять: на PostgreSQL LIKE регистрозависим. */
    #[Test]
    public function поиск_не_зависит_от_регистра(): void
    {
        $this->listing(['title' => 'Цемент М400 навалом']);

        $this->get('/catalog?q=ЦЕМЕНТ')
            ->assertInertia(fn (AssertableInertia $page) => $page->has('listings.data', 1));
    }

    #[Test]
    public function фильтр_раздела_включает_подкатегории(): void
    {
        $parent = Category::create(['slug' => 'stroymaterialy', 'is_active' => true]);
        $parent->translations()->create(['locale' => 'ru', 'name' => 'Стройматериалы']);

        $child = Category::create(['slug' => 'cement', 'parent_id' => $parent->id, 'is_active' => true]);
        $child->translations()->create(['locale' => 'ru', 'name' => 'Цемент']);

        $this->listing(['title' => 'Цемент М400', 'category_id' => $child->id]);
        $this->listing(['title' => 'Пряжа хлопковая', 'category_id' => null]);

        // Выбран раздел — объявление из его подкатегории должно найтись
        $this->get("/catalog?category={$parent->id}")
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('listings.data', 1)
                ->where('listings.data.0.title', 'Цемент М400'),
            );
    }

    #[Test]
    public function фильтр_по_типу_разделяет_предложения_и_запросы(): void
    {
        $this->listing(['title' => 'Продаю цемент', 'type' => Listing::TYPE_SUPPLY]);
        $this->listing(['title' => 'Куплю поддоны', 'type' => Listing::TYPE_DEMAND]);

        $this->get('/catalog?type=demand')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('listings.data', 1)
                ->where('listings.data.0.title', 'Куплю поддоны'),
            );
    }

    /**
     * Продвижение поднимает объявление, но не подменяет выдачу:
     * органика остаётся в списке, а платное помечается.
     */
    #[Test]
    public function продвинутое_объявление_выше_и_помечено(): void
    {
        $old = $this->listing(['title' => 'Обычное свежее', 'published_at' => now()]);
        $promoted = $this->listing(['title' => 'Продвинутое старое', 'published_at' => now()->subMonth()]);

        $type = PromotionType::create([
            'code' => 'category_top',
            'name' => 'ТОП категории',
            'description' => 'Первые позиции',
            'cost_units' => 5,
            'duration_days' => 7,
            'badge' => 'ТОП',
        ]);

        Promotion::create([
            'listing_id' => $promoted->id,
            'company_id' => $this->company->id,
            'promotion_type_id' => $type->id,
            'units_spent' => 5,
            'status' => 'active',
            'starts_at' => now()->subDay(),
            'ends_at' => now()->addDays(6),
            'impressions_before' => 0,
        ]);

        $this->get('/catalog')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('listings.data.0.title', 'Продвинутое старое')
                ->where('listings.data.0.promoted', true)
                ->where('listings.data.0.badges.0', 'ТОП')
                // Органика не выброшена — она следующая
                ->where('listings.data.1.title', $old->title)
                ->where('listings.data.1.promoted', false),
            );
    }

    #[Test]
    public function показы_и_поисковые_запросы_записываются(): void
    {
        $listing = $this->listing(['title' => 'Цемент М400']);

        $this->get('/catalog?q=цемент');

        $this->assertSame(1, $listing->fresh()->impressions_count);
        $this->assertSame(1, ListingStat::where('listing_id', $listing->id)->value('impressions'));

        // Запрос засчитывается компании — на этом строится отчёт
        // «по каким запросам вас находили»
        $hit = SearchHit::where('company_id', $this->company->id)->first();

        $this->assertNotNull($hit);
        $this->assertSame('цемент', $hit->query);
    }

    #[Test]
    public function карточка_объявления_открывается_и_считает_просмотр(): void
    {
        $listing = $this->listing(['title' => 'Цемент М400 навалом']);

        $this->get("/listing/{$listing->slug}")
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->component('catalog/Show')
                ->where('listing.title', 'Цемент М400 навалом')
                ->where('company.name', 'ООО «Стройбаза»'),
            );

        $this->assertSame(1, $listing->fresh()->views_count);
    }

    #[Test]
    public function на_карточке_контакты_замаскированы_для_гостя(): void
    {
        CompanyContact::create([
            'company_id' => $this->company->id,
            'type' => 'phone',
            'value' => '+998 90 555-11-22',
            'is_public' => true,
        ]);

        $listing = $this->listing();

        $this->get("/listing/{$listing->slug}")
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('unlocked', false)
                ->where('contacts.0.locked', true),
            )
            ->assertDontSee('555-11-22');
    }

    #[Test]
    public function оплаченные_контакты_видны_на_карточке(): void
    {
        CompanyContact::create([
            'company_id' => $this->company->id,
            'type' => 'phone',
            'value' => '+998 90 555-11-22',
            'is_public' => true,
        ]);

        $buyerCompany = Company::factory()->create();
        $buyer = User::factory()->create(['company_id' => $buyerCompany->id]);

        ContactUnlock::create([
            'company_id' => $buyerCompany->id,
            'target_company_id' => $this->company->id,
            'credits_spent' => 1,
        ]);

        $listing = $this->listing();

        $this->actingAs($buyer)
            ->get("/listing/{$listing->slug}")
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('unlocked', true)
                ->where('contacts.0.value', '+998 90 555-11-22'),
            );
    }

    #[Test]
    public function неопубликованное_объявление_недоступно_по_адресу(): void
    {
        $draft = $this->listing(['status' => Listing::STATUS_DRAFT]);

        $this->get("/listing/{$draft->slug}")->assertNotFound();
    }
}
