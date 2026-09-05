<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Category;
use App\Models\Tender;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Витрина тендеров — отдельный раздел рядом с каталогом.
 *
 * Показываются только опубликованные; по умолчанию — те, у которых
 * не прошёл срок подачи заявок. Завершённые доступны отдельной
 * вкладкой, черновики не видны никому.
 */
class TendersTest extends TestCase
{
    use RefreshDatabase;

    #[Test]
    public function список_показывает_только_опубликованные_и_открытые(): void
    {
        $open = Tender::factory()->create(['title' => 'Поставка цемента для школы']);
        Tender::factory()->draft()->create(['title' => 'Черновик закупки']);
        Tender::factory()->closed()->create(['title' => 'Завершённая закупка']);

        $this->get('/tenders')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->component('tenders/Index')
                ->where('total', 1)
                ->where('tenders.data.0.slug', $open->slug)
                ->where('tenders.data.0.title', 'Поставка цемента для школы')
                ->where('tenders.data.0.closed', false));
    }

    #[Test]
    public function вкладка_завершённых_показывает_прошедшие_сроки(): void
    {
        Tender::factory()->create(['title' => 'Открытая закупка']);
        $closed = Tender::factory()->closed()->create(['title' => 'Завершённая закупка']);

        $this->get('/tenders?closed=1')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('total', 1)
                ->where('tenders.data.0.slug', $closed->slug)
                ->where('tenders.data.0.closed', true)
                ->where('filters.closed', true));
    }

    #[Test]
    public function поиск_находит_по_заголовку_описанию_и_заказчику(): void
    {
        Tender::factory()->create(['title' => 'Поставка арматуры', 'description' => 'Сталь А500С', 'customer' => 'ГУП «Мостстрой»']);
        Tender::factory()->create(['title' => 'Закупка пряжи', 'description' => 'Хлопок 30/1', 'customer' => 'ООО «Текстиль»']);

        $this->get('/tenders?q=мостстрой')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('total', 1)
                ->where('tenders.data.0.title', 'Поставка арматуры'));

        $this->get('/tenders?q=хлопок')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('total', 1)
                ->where('tenders.data.0.title', 'Закупка пряжи'));
    }

    #[Test]
    public function фильтр_по_разделу_включает_подкатегории(): void
    {
        $parent = Category::factory()->named('Стройматериалы')->create();
        $child = Category::factory()->named('Цемент')->child($parent)->create();
        $other = Category::factory()->named('Текстиль')->create();

        Tender::factory()->create(['title' => 'Цемент М400', 'category_id' => $child->id]);
        Tender::factory()->create(['title' => 'Пряжа', 'category_id' => $other->id]);

        $this->get("/tenders?category={$parent->id}")
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('total', 1)
                ->where('tenders.data.0.title', 'Цемент М400')
                ->where('tenders.data.0.category', 'Цемент'));
    }

    #[Test]
    public function открытые_сортируются_по_ближайшему_сроку(): void
    {
        Tender::factory()->create(['title' => 'Через месяц', 'deadline_at' => now()->addDays(30)]);
        Tender::factory()->create(['title' => 'Без срока', 'deadline_at' => null]);
        Tender::factory()->create(['title' => 'Через неделю', 'deadline_at' => now()->addDays(7)]);

        $this->get('/tenders')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('tenders.data.0.title', 'Через неделю')
                ->where('tenders.data.1.title', 'Через месяц')
                ->where('tenders.data.2.title', 'Без срока')
                ->where('tenders.data.0.days_left', 7));
    }

    #[Test]
    public function карточка_открывается_и_считает_просмотры(): void
    {
        $tender = Tender::factory()->create([
            'title' => 'Поставка металлопроката',
            'description' => "Первый абзац.\n\nВторой абзац.",
            'budget' => 250_000_000,
            'contact_phone' => '+998 71 200-00-00',
            'source_url' => 'https://xarid.uzex.uz/lot/1',
        ]);

        $this->get("/tenders/{$tender->slug}")
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->component('tenders/Show')
                ->where('tender.title', 'Поставка металлопроката')
                ->where('tender.description', ['Первый абзац.', 'Второй абзац.'])
                ->where('tender.budget', 250_000_000)
                ->where('tender.contact_phone', '+998 71 200-00-00')
                ->where('tender.source_url', 'https://xarid.uzex.uz/lot/1'));

        $this->assertSame(1, $tender->fresh()->views_count);
    }

    #[Test]
    public function черновик_и_отложенная_публикация_не_открываются(): void
    {
        $draft = Tender::factory()->draft()->create();
        $future = Tender::factory()->create(['published_at' => now()->addDay()]);

        $this->get("/tenders/{$draft->slug}")->assertNotFound();
        $this->get("/tenders/{$future->slug}")->assertNotFound();
        $this->get('/tenders')->assertInertia(fn (AssertableInertia $page) => $page->where('total', 0));
    }

    #[Test]
    public function адрес_строится_из_заголовка_и_id(): void
    {
        $tender = Tender::factory()->create(['title' => 'Поставка цемента М400']);

        $this->assertSame('postavka-tsementa-m400-'.$tender->id, $tender->slug);
    }

    #[Test]
    public function на_другом_языке_отдаётся_перевод_с_откатом_на_русский(): void
    {
        $tender = Tender::factory()->create(['title' => 'Поставка цемента']);
        $tender->forceFill(['title_i18n' => ['en' => 'Cement supply']])->save();

        $this->get("/en/tenders/{$tender->slug}")
            ->assertInertia(fn (AssertableInertia $page) => $page->where('tender.title', 'Cement supply'));

        $this->get("/uz/tenders/{$tender->slug}")
            ->assertInertia(fn (AssertableInertia $page) => $page->where('tender.title', 'Поставка цемента'));
    }

    #[Test]
    public function карта_сайта_знает_о_тендерах(): void
    {
        $tender = Tender::factory()->create();

        $this->get('/sitemap.xml')->assertOk()->assertSee(url('/sitemap-tenders.xml'), false);
        $this->get('/sitemap-tenders.xml')->assertOk()->assertSee(url('/tenders/'.$tender->slug), false);
        $this->get('/sitemap-static.xml')->assertOk()->assertSee(url('/tenders'), false);
    }
}
