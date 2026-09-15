<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Category;
use App\Models\Company;
use App\Models\Listing;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Загруженное из книги объявление без перевода на языке не показывается.
 *
 * Правило разное для двух источников. Написанное в кабинете переводов
 * могло не иметь никогда — на английской версии оно показывается
 * по-русски: русский текст лучше пустой выдачи. Загруженное из книги
 * переводят руками, и без перевода на английской версии оно висело
 * бы по-русски среди английских карточек — его не показываем вовсе.
 *
 * Прямая ссылка при этом открывается: её присылают в мессенджерах
 * и по ней приходит поисковик, и 404 сломал бы обе дороги. Открыв
 * её, человек видит русский текст, а поисковик — каноническую
 * ссылку на русскую версию и hreflang без английской.
 */
class ImportedListingVisibilityTest extends TestCase
{
    use RefreshDatabase;

    private Company $company;

    protected function setUp(): void
    {
        parent::setUp();

        $this->company = Company::factory()->create(['status' => 'active']);
    }

    /** @param array<string, mixed> $overrides */
    private function listing(array $overrides = []): Listing
    {
        return Listing::factory()->create([
            'company_id' => $this->company->id,
            'status' => Listing::STATUS_ACTIVE,
            'published_at' => now()->subDay(),
            'expires_at' => now()->addDays(30),
            ...$overrides,
        ]);
    }

    #[Test]
    public function загруженное_без_перевода_скрыто_на_этом_языке_и_видно_на_остальных(): void
    {
        $this->listing([
            'title' => 'Кирпич керамический М150',
            'source' => Listing::SOURCE_IMPORT,
            'title_i18n' => ['uz' => 'Keramik g‘isht M150'],
        ]);

        // Русская версия — всегда
        $this->get('/catalog')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('listings.data', 1)
                ->where('listings.data.0.title', 'Кирпич керамический М150'));

        // Узбекский перевод есть — показывается им
        $this->get('/uz/catalog')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('listings.data', 1)
                ->where('listings.data.0.title', 'Keramik g‘isht M150'));

        // Английского нет — объявления на английской версии нет
        $this->get('/en/catalog')
            ->assertInertia(fn (AssertableInertia $page) => $page->has('listings.data', 0));
    }

    #[Test]
    public function написанное_в_кабинете_без_перевода_показывается_по_русски(): void
    {
        $this->listing([
            'title' => 'Цементные бриз-блоки',
            'source' => Listing::SOURCE_CABINET,
            'title_i18n' => null,
        ]);

        $this->get('/en/catalog')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('listings.data', 1)
                ->where('listings.data.0.title', 'Цементные бриз-блоки'));
    }

    #[Test]
    public function поиск_не_находит_скрытое_по_русскому_тексту(): void
    {
        $this->listing([
            'title' => 'Кирпич керамический М150',
            'source' => Listing::SOURCE_IMPORT,
            'title_i18n' => null,
        ]);

        $this->get('/en/catalog?q=кирпич')
            ->assertInertia(fn (AssertableInertia $page) => $page->has('listings.data', 0));
    }

    #[Test]
    public function прямая_ссылка_на_скрытое_открывает_русскую_версию(): void
    {
        $listing = $this->listing([
            'title' => 'Кирпич керамический М150',
            'source' => Listing::SOURCE_IMPORT,
            'title_i18n' => ['uz' => 'Keramik g‘isht M150'],
        ]);

        $response = $this->get('/en/listing/'.$listing->slug);

        $response->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('listing.title', 'Кирпич керамический М150'));

        // Поисковику: каноническая — русская, английской версии нет,
        // узбекская есть
        $response
            ->assertSee('rel="canonical" href="'.url('/listing/'.$listing->slug).'"', false)
            ->assertSee('hreflang="uz" href="'.url('/uz/listing/'.$listing->slug).'"', false)
            ->assertDontSee('hreflang="en"', false);

        // На языке с переводом — обычная страница со своей канонической
        $this->get('/uz/listing/'.$listing->slug)
            ->assertOk()
            ->assertSee('rel="canonical" href="'.url('/uz/listing/'.$listing->slug).'"', false);
    }

    #[Test]
    public function похожие_и_счётчики_категорий_не_видят_скрытое(): void
    {
        $category = Category::factory()->named('Стройматериалы')->create();

        $shown = $this->listing([
            'title' => 'Цементные бриз-блоки',
            'category_id' => $category->id,
            'source' => Listing::SOURCE_CABINET,
        ]);
        $this->listing([
            'title' => 'Кирпич керамический М150',
            'category_id' => $category->id,
            'source' => Listing::SOURCE_IMPORT,
            'title_i18n' => null,
        ]);

        // Сначала русская версия: после «/en/…» сессия запоминает язык,
        // и адрес без префикса уводился бы редиректом
        $this->get('/listing/'.$shown->slug)
            ->assertInertia(fn (AssertableInertia $page) => $page->has('similar', 1));

        $this->get('/en/catalog')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('listings.data', 1)
                ->where('listings.data.0.title', 'Цементные бриз-блоки'));

        $this->get('/en/listing/'.$shown->slug)
            ->assertInertia(fn (AssertableInertia $page) => $page->has('similar', 0));
    }

    #[Test]
    public function главная_и_визитка_считают_только_видимое(): void
    {
        $this->listing([
            'type' => Listing::TYPE_DEMAND,
            'title' => 'Куплю цемент М400',
            'source' => Listing::SOURCE_IMPORT,
            'title_i18n' => null,
        ]);
        $this->listing([
            'type' => Listing::TYPE_DEMAND,
            'title' => 'Куплю щебень',
            'source' => Listing::SOURCE_CABINET,
        ]);

        // Русская версия первой — см. выше про запомненный язык
        $this->get('/company/'.$this->company->slug)
            ->assertInertia(fn (AssertableInertia $page) => $page->where('listings_count', 2));

        $this->get('/en')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('requests', 1)
                ->where('stats.listings', 1));

        $this->get('/en/company/'.$this->company->slug)
            ->assertInertia(fn (AssertableInertia $page) => $page->where('listings_count', 1));
    }

    #[Test]
    public function карта_сайта_не_обещает_скрытые_языки(): void
    {
        $listing = $this->listing([
            'title' => 'Кирпич керамический М150',
            'source' => Listing::SOURCE_IMPORT,
            'title_i18n' => ['uz' => 'Keramik g‘isht M150'],
        ]);

        $this->get('/sitemap-listings-1.xml')
            ->assertOk()
            ->assertSee('<loc>'.url('/listing/'.$listing->slug).'</loc>', false)
            ->assertSee('<loc>'.url('/uz/listing/'.$listing->slug).'</loc>', false)
            ->assertDontSee('<loc>'.url('/en/listing/'.$listing->slug).'</loc>', false)
            ->assertDontSee('hreflang="en"', false);
    }
}
