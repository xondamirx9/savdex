<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\LandingBlock;
use App\Models\User;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Главная страница с текстами из админки.
 *
 * Раньше главная брала тексты из словаря, а «Блоки главной» правили
 * таблицу, которую сайт не читал. Теперь (решение заказчика) из
 * админки правятся тексты, вопросы и видимость секций; порядок — как
 * в макете. Тексты перенесла миграция такими, какими их показывал сайт.
 *
 * Раздел админки — на Python (python/savdex/site/landing_admin.py,
 * проверки — python/tests/test_landing_admin.py).
 */
class HomeBlocksTest extends TestCase
{
    use RefreshDatabase;

    private function block(string $key): LandingBlock
    {
        return LandingBlock::query()->where('key', $key)->firstOrFail();
    }

    #[Test]
    public function миграция_перенесла_тексты_сайта_и_убрала_старые_блоки(): void
    {
        $this->assertSame(LandingBlock::KEYS, LandingBlock::query()->orderBy('sort')->pluck('key')->all());

        $this->get('/')->assertInertia(fn (AssertableInertia $page) => $page
            ->component('Home')
            ->where('blocks.hero.heading', 'Поставщики и закупщики находят друг друга')
            ->where('blocks.how.items.0', [
                'title' => 'Зарегистрируйтесь',
                'text' => 'Почта, пароль, данные компании. Две минуты, карта не нужна.',
            ])
            ->has('blocks.how.items', 4)
            ->has('blocks.faq.items', 6)
            ->where('blocks.cta.button', 'Зарегистрироваться')
            ->where('blocks.cta.note', 'Бесплатно · 4 объявления · 3 контакта в месяц · без привязки карты'));
    }

    #[Test]
    public function свой_текст_языка(): void
    {
        $this->get('/uz')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('blocks.news.heading', fn (string $heading) => $heading !== '' && $heading !== 'Новости площадки'));

        $this->block('hero')->update(['heading_i18n' => ['uz' => 'Yangi sarlavha']]);

        $this->get('/uz')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('blocks.hero.heading', 'Yangi sarlavha'));
    }

    #[Test]
    public function незаполненный_язык_уходит_в_машинный_перевод_по_пунктам(): void
    {
        $this->block('how')->update(['body' => "Шаг один\nПояснение", 'body_i18n' => null]);
        DB::table('content_translations')->insert([
            'hash' => sha1('Шаг один'), 'locale' => 'en', 'source' => 'Шаг один',
            'translation' => 'Step one', 'attempts' => 1, 'created_at' => now(), 'updated_at' => now(),
        ]);

        $this->get('/en')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('blocks.how.items', [['title' => 'Step one', 'text' => 'Пояснение']]));

        // Непереведённая строка встала в очередь переводчика
        $this->assertDatabaseHas('content_translations', ['locale' => 'en', 'source' => 'Пояснение']);
    }

    #[Test]
    public function скрытая_секция_и_её_разметка_для_поисковика(): void
    {
        // Один запрос на тест: разметка Seo живёт в пределах теста
        $this->block('faq')->update(['is_visible' => false]);
        $this->block('stats')->update(['is_visible' => false]);

        $response = $this->get('/')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('blocks.faq.visible', false)
            ->where('blocks.stats.visible', false));

        $this->assertStringNotContainsString('FAQPage', (string) $response->getContent());
    }

    #[Test]
    public function первый_экран_не_скрывается(): void
    {
        $this->block('hero')->update(['is_visible' => false]);

        $this->get('/')->assertInertia(fn (AssertableInertia $page) => $page->where('blocks.hero.visible', true));
    }

    #[Test]
    public function вопросы_для_поисковика_те_же_что_на_странице(): void
    {
        $this->block('faq')->update(['body' => "Можно ли по счёту?\nДа, для юрлиц."]);

        $html = (string) $this->get('/')->getContent();

        $this->assertStringContainsString('FAQPage', $html);
        $this->assertStringContainsString('Можно ли по счёту?', html_entity_decode($html));
        $this->assertStringNotContainsString('Сколько стоит размещение объявлений?', html_entity_decode($html));
    }

    #[Test]
    public function пункт_меню_ведёт_в_раздел_на_python(): void
    {
        $admin = fn (string $role) => User::factory()->create(['is_admin' => true, 'admin_role' => $role, 'status' => 'active']);
        $link = '/admin/python?next=/py/admin/site/landingblock/';

        $this->actingAs($admin(AdminAccess::CONTENT_MANAGER));
        $this->get('/admin')->assertSee($link, false);

        $this->actingAs($admin(AdminAccess::SALES));
        $this->get('/admin')->assertDontSee($link, false);
    }

    #[Test]
    public function пункты_из_текста(): void
    {
        $this->assertSame([
            ['title' => 'Вопрос', 'text' => 'Ответ в две строки'],
            ['title' => 'Без ответа', 'text' => ''],
        ], LandingBlock::parseItems("Вопрос\r\nОтвет\nв две строки\n \nБез ответа\n"));
    }
}
