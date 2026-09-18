<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Banner;
use App\Support\BannerCard;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Carbon;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Баннер на сайте.
 *
 * Логика сроков проверена отдельно; здесь — что она доходит до живых
 * страниц. Раздел в админке, который не влияет на витрину, бесполезен.
 */
class BannerDisplayTest extends TestCase
{
    use RefreshDatabase;

    private function banner(array $attrs = []): Banner
    {
        return Banner::query()->create(array_merge([
            'name' => 'Осенняя акция',
            'placement' => Banner::PLACEMENT_HOME,
            'alt' => 'Скидка 30% на годовой тариф',
            'image_path' => 'banners/autumn.webp',
        ], $attrs));
    }

    #[Test]
    public function баннер_доходит_до_главной(): void
    {
        $this->banner(['url' => 'https://savdex.uz/pricing']);

        $this->get('/')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('banner.alt', 'Скидка 30% на годовой тариф')
            ->where('banner.url', 'https://savdex.uz/pricing'));
    }

    #[Test]
    public function баннер_доходит_до_каталога(): void
    {
        $this->banner(['placement' => Banner::PLACEMENT_CATALOG]);

        $this->get('/catalog')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('banner.alt', 'Скидка 30% на годовой тариф'));
    }

    /** Нет акции — нет и пустого места на странице. */
    #[Test]
    public function без_баннера_страница_отдаёт_пусто(): void
    {
        $this->get('/')->assertInertia(fn (AssertableInertia $page) => $page->where('banner', null));
    }

    /** Запланированный на будущее до срока на витрину не попадает. */
    #[Test]
    public function запланированный_баннер_на_витрину_не_попадает(): void
    {
        $this->banner(['starts_at' => Carbon::now()->addWeek()]);

        $this->get('/')->assertInertia(fn (AssertableInertia $page) => $page->where('banner', null));
    }

    /** Истёкший исчезает с витрины сам. */
    #[Test]
    public function истёкший_баннер_с_витрины_исчезает(): void
    {
        $this->banner(['ends_at' => Carbon::now()->subHour()]);

        $this->get('/')->assertInertia(fn (AssertableInertia $page) => $page->where('banner', null));
    }

    /** Баннер каталога на главную не лезет. */
    #[Test]
    public function места_не_путаются(): void
    {
        $this->banner(['placement' => Banner::PLACEMENT_CATALOG]);

        $this->get('/')->assertInertia(fn (AssertableInertia $page) => $page->where('banner', null));
    }

    // ── Языки ───────────────────────────────────────────────────────

    /** Загрузили картинку под язык — показывается она. */
    #[Test]
    public function картинка_под_язык_побеждает_основную(): void
    {
        $banner = $this->banner();
        $banner->images()->create(['locale' => 'zh', 'image_path' => 'banners/autumn-zh.webp']);
        $banner->load('images');

        $this->assertStringContainsString('autumn-zh', $banner->imageFor('zh'));
        $this->assertStringContainsString('autumn.webp', $banner->imageFor('ru'), 'для русского остаётся основная');
    }

    /**
     * Мобильная картинка чужого языка не подставляется.
     *
     * На ней был бы чужой текст. Лучше обрезать свою широкую
     * по точке фокуса, чем показать китайцу русскую акцию.
     */
    #[Test]
    public function мобильная_картинка_чужого_языка_не_подставляется(): void
    {
        $banner = $this->banner(['image_mobile_path' => 'banners/autumn-mobile.webp']);
        $banner->images()->create(['locale' => 'zh', 'image_path' => 'banners/autumn-zh.webp']);
        $banner->load('images');

        $this->assertNull($banner->mobileImageFor('zh'), 'русская мобильная картинка китайцу не подходит');
        $this->assertSame('banners/autumn-mobile.webp', $banner->mobileImageFor('ru'));
    }

    // ── Что уходит на страницу ──────────────────────────────────────

    /** Ключ закрытия содержит номер: закрытая акция не прячет новую. */
    #[Test]
    public function ключ_закрытия_привязан_к_баннеру(): void
    {
        $first = $this->banner(['sort' => 1]);
        $card = BannerCard::forPlacement(Banner::PLACEMENT_HOME);

        $this->assertSame('banner-'.$first->id, $card['key']);
    }

    #[Test]
    public function точка_фокуса_уходит_на_страницу(): void
    {
        $this->banner(['focal_x' => 20, 'focal_y' => 80]);

        $this->assertSame('20% 80%', BannerCard::forPlacement(Banner::PLACEMENT_HOME)['focal']);
    }
}
