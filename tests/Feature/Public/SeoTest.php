<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Category;
use App\Models\Company;
use App\Models\Listing;
use App\Models\Review;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Мета-теги, отдаваемые сервером.
 *
 * Проверяется именно HTML первого ответа, а не то, что дорисует
 * скрипт: превью-боты Telegram и WhatsApp JavaScript не выполняют
 * вовсе, а Яндекс отрисовывает его неохотно. До этого исправления
 * робот получал страницу без заголовка, описания и h1 — а ссылка
 * на объявление в Telegram выглядела голым адресом.
 */
class SeoTest extends TestCase
{
    use RefreshDatabase;

    private function listing(array $overrides = []): Listing
    {
        $category = Category::factory()->named('Стройматериалы')->create();

        return Listing::factory()->create([
            'category_id' => $category->id,
            'status' => Listing::STATUS_ACTIVE,
            'published_at' => now()->subDay(),
            ...$overrides,
        ]);
    }

    // ── Базовые теги ─────────────────────────────────────────

    /** @return list<array{string}> */
    public static function публичныеСтраницы(): array
    {
        return [['/'], ['/catalog'], ['/companies'], ['/pricing'], ['/about'], ['/news']];
    }

    #[Test]
    #[DataProvider('публичныеСтраницы')]
    public function страница_отдаёт_заголовок_и_описание_в_html(string $url): void
    {
        $response = $this->get($url);

        $response->assertOk();
        $response->assertSee('<title inertia>', false);
        $response->assertSee('· SAVDEX</title>', false);
        $response->assertSee('name="description"', false);
        $response->assertSee('rel="canonical"', false);
        $response->assertSee('property="og:title"', false);
    }

    #[Test]
    public function карточка_объявления_описана_своим_заголовком(): void
    {
        $listing = $this->listing(['title' => 'Цемент М400 навалом с завода']);

        $this->get("/listing/{$listing->slug}")
            ->assertSee('Цемент М400 навалом с завода', false)
            ->assertSee('property="og:type" content="product"', false)
            ->assertSee('"@type":"Product"', false)
            ->assertSee('"@type":"BreadcrumbList"', false);
    }

    /** Разметка Offer даёт в выдаче цену рядом со ссылкой. */
    #[Test]
    public function цена_попадает_в_разметку(): void
    {
        $listing = $this->listing(['price' => 1250000, 'currency' => 'UZS', 'price_negotiable' => false]);

        $this->get("/listing/{$listing->slug}")
            ->assertSee('"@type":"Offer"', false)
            ->assertSee('"price":1250000', false)
            ->assertSee('"priceCurrency":"UZS"', false);
    }

    /**
     * Договорная цена — честный случай «предложения нет».
     * Offer без цены поисковик считает неполным и не показывает вовсе.
     */
    #[Test]
    public function договорная_цена_не_даёт_пустого_предложения(): void
    {
        $listing = $this->listing(['price' => null, 'price_negotiable' => true]);

        $this->get("/listing/{$listing->slug}")->assertDontSee('"@type":"Offer"', false);
    }

    #[Test]
    public function визитка_компании_описана_и_размечена(): void
    {
        $company = Company::factory()->create(['name' => 'ООО «Стройбаза»', 'tin' => '304561278']);

        $this->get("/company/{$company->slug}")
            ->assertSee('ООО «Стройбаза»', false)
            ->assertSee('"@type":"Organization"', false)
            ->assertSee('304561278', false);
    }

    /**
     * Название компании задаёт пользователь и печатается внутри
     * <script type="application/ld+json">. Угловые скобки обязаны
     * шифроваться: «</script>» в названии иначе закрывает тег и
     * исполняет чужой скрипт на каждой визитке (XSS).
     */
    #[Test]
    public function разметка_не_даёт_вырваться_из_script_через_название(): void
    {
        $company = Company::factory()->create([
            'name' => '</script><script>alert(1)</script>',
        ]);

        $response = $this->get("/company/{$company->slug}");
        $response->assertOk();

        // Настоящая сигнатура прорыва — закрывающий тег вплотную к
        // открывающему — в сыром HTML не встречается ни в одном блоке:
        // в JSON-LD скобки шифруются (JSON_HEX_TAG), в пропсах Inertia
        // экранируется слэш (<\/script>), и тег не закрывается.
        $response->assertDontSee('</script><script>alert(1)', false);
        // А в самом JSON-LD название присутствует в безопасном виде
        $response->assertSee('\\u003Cscript\\u003Ealert(1)', false);
    }

    /**
     * Рейтинг в разметке — только при отзывах.
     *
     * Звёзды в выдаче при нуле отзывов — заявка, за которой ничего
     * не стоит, и поисковики за такое понижают.
     */
    #[Test]
    public function рейтинг_без_отзывов_не_размечается(): void
    {
        $company = Company::factory()->create(['rating' => 0, 'reviews_count' => 0]);

        $this->get("/company/{$company->slug}")->assertDontSee('aggregateRating', false);
    }

    #[Test]
    public function рейтинг_с_отзывами_размечается(): void
    {
        $company = Company::factory()->create();
        Review::factory()->count(3)->create(['company_id' => $company->id, 'rating' => 5]);
        $this->artisan('ratings:recalculate');

        $this->get("/company/{$company->slug}")
            ->assertSee('"@type":"AggregateRating"', false)
            ->assertSee('"reviewCount":3', false);
    }

    // ── Превью ссылки ────────────────────────────────────────

    /**
     * Объявление без фотографий всё равно даёт крупное превью.
     *
     * Пустой og:image превращает ссылку в Telegram в узкую строчку,
     * которую в переписке не замечают, — а Telegram здесь основной
     * канал распространения.
     */
    #[Test]
    public function объявление_без_фото_получает_фирменную_заглушку(): void
    {
        $listing = $this->listing();

        $this->get("/listing/{$listing->slug}")
            ->assertSee('property="og:image" content="'.url('/og-cover.png').'"', false)
            ->assertSee('content="summary_large_image"', false);
    }

    #[Test]
    public function заглушка_превью_лежит_на_диске(): void
    {
        $path = public_path('og-cover.png');

        $this->assertFileExists($path);
        // Пропорции 1.91:1 — то, что Telegram и Facebook показывают
        // целиком; квадрат они обрезают сверху и снизу
        $this->assertSame([1200, 630], array_slice((array) getimagesize($path), 0, 2));
    }

    // ── Дубли ────────────────────────────────────────────────

    /**
     * Фильтры дают тысячи адресов с почти одинаковым содержимым.
     * Каждый в индексе конкурирует с каталогом за одни запросы.
     */
    #[Test]
    public function каталог_с_фильтром_закрыт_от_индексации(): void
    {
        $this->get('/catalog?q=цемент')->assertSee('content="noindex, follow"', false);
        $this->get('/catalog?city=1')->assertSee('content="noindex, follow"', false);
    }

    #[Test]
    public function чистый_каталог_индексируется(): void
    {
        $this->get('/catalog')->assertDontSee('noindex', false);
    }

    /** Канонический адрес фильтрованной страницы ведёт на основную. */
    #[Test]
    public function фильтры_указывают_на_канонический_каталог(): void
    {
        $this->get('/catalog?q=цемент&sort=cheap')
            ->assertSee('rel="canonical" href="'.url('/catalog').'"', false);
    }

    #[Test]
    public function заголовок_из_запроса_начинается_с_заглавной(): void
    {
        $this->get('/catalog?q=цемент')->assertSee('<title inertia>Цемент', false);
    }

    // ── Карта сайта и robots ─────────────────────────────────

    #[Test]
    public function карта_сайта_перечисляет_разделы(): void
    {
        $this->get('/sitemap.xml')
            ->assertOk()
            ->assertHeader('Content-Type', 'application/xml; charset=utf-8')
            ->assertSee('sitemap-static.xml', false)
            ->assertSee('sitemap-companies.xml', false)
            ->assertSee('sitemap-listings-1.xml', false);
    }

    #[Test]
    public function карта_сайта_содержит_активные_объявления(): void
    {
        $listing = $this->listing();
        $draft = Listing::factory()->draft()->create();

        $response = $this->get('/sitemap-listings-1.xml');

        $response->assertSee(url('/listing/'.$listing->slug), false);
        // Черновик и снятое объявление роботу присылать незачем:
        // он придёт на 404 и в следующий раз зайдёт нескоро
        $response->assertDontSee(url('/listing/'.$draft->slug), false);
    }

    #[Test]
    public function пустая_категория_в_карту_не_попадает(): void
    {
        $empty = Category::factory()->named('Пустая')->create();
        $listing = $this->listing();

        $response = $this->get('/sitemap-categories.xml');

        $response->assertDontSee('category='.$empty->id, false);
        $response->assertSee('category='.$listing->category_id, false);
    }

    /** Оферту ищут по названию площадки перед оплатой. */
    #[Test]
    public function юридические_страницы_описаны_и_есть_в_карте(): void
    {
        $this->get('/terms')
            ->assertSee('<title inertia>Публичная оферта · SAVDEX</title>', false)
            ->assertSee('rel="canonical" href="'.url('/terms').'"', false);

        $this->get('/sitemap-static.xml')
            ->assertSee(url('/terms'), false)
            ->assertSee(url('/privacy'), false);
    }

    #[Test]
    public function неизвестный_раздел_карты_отдаёт_404(): void
    {
        $this->get('/sitemap-nonsense.xml')->assertNotFound();
    }

    /** Робот не должен тратить лимит обхода на кабинет и админку. */
    #[Test]
    public function robots_закрывает_приватные_разделы(): void
    {
        $response = $this->get('/robots.txt');

        $response->assertOk();
        $response->assertSee('Disallow: /cabinet');
        $response->assertSee('Disallow: /admin');
        // Сортировка бывает и первым параметром, и после фильтра
        $response->assertSee('Disallow: /*?sort=', false);
        $response->assertSee('Disallow: /*&sort=', false);
        // Адрес карты по спецификации абсолютный
        $response->assertSee('Sitemap: '.url('/sitemap.xml'));
    }
}
