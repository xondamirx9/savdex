<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Filament\Widgets\ContentDrafts;
use App\Models\FaqItem;
use App\Models\Page;
use App\Models\User;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use Inertia\Testing\AssertableInertia;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Страницы о площадке с текстом из админки.
 *
 * Раньше «О компании», «Помощь», «Инструкция» и «Правила» брали текст
 * из словаря, а раздел «Страницы и FAQ» правил таблицу, которую сайт
 * не читал: правка никуда не доходила. Теперь:
 *
 * - тексты — из базы, со своими полями под каждый язык; перенесла их
 *   миграция такими, какими их показывал сайт;
 * - язык, который не заполнили, показывается машинным переводом;
 * - «Помощь», «Инструкция», «Правила» — по своим адресам, а старые
 *   ссылки /about#help ведут туда (это делает сама страница: якорь до
 *   сервера не доходит).
 *
 * Раздел админки — на Python (python/savdex/site/pages_admin.py,
 * проверки — python/tests/test_pages_admin.py).
 */
class DocPagesTest extends TestCase
{
    use RefreshDatabase;

    /** @return array<string, array{string, string, string}> */
    public static function страницы(): array
    {
        return [
            'помощь' => ['help', 'Помощь', 'Сколько стоит разместить объявление?'],
            'инструкция' => ['guide', 'Инструкция использования', 'Если вы поставщик'],
            'правила' => ['rules', 'Правила размещения', 'Контактные данные в тексте объявления запрещены.'],
        ];
    }

    #[Test]
    #[DataProvider('страницы')]
    public function страница_по_своему_адресу_с_прежним_текстом(string $key, string $title, string $text): void
    {
        $this->get('/'.$key)
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->component('DocPage')
                ->where('page.key', $key)
                ->where('page.title', $title)
                ->where('page', fn ($card) => str_contains(json_encode([$card, $page->toArray()['props']['faq']], JSON_UNESCAPED_UNICODE), $text))
                ->where('nav.0.href', '/about'));
    }

    #[Test]
    public function инструкция_и_правила_разбиты_на_блоки(): void
    {
        $this->get('/guide')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('page.blocks.0', ['type' => 'heading', 'text' => 'Если вы поставщик'])
            ->where('page.blocks.1.type', 'steps')
            ->where('page.blocks.1.items.0.title', 'Зарегистрируйтесь и подтвердите почту.')
            ->where('page.blocks.1.items.0.hint', 'До подтверждения кабинет доступен, но публиковать нельзя.')
            ->has('page.blocks.1.items', 4)
            ->has('page.blocks.3.items', 3));

        $this->get('/rules')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('page.blocks.0.type', 'note')
            ->where('page.blocks.2.type', 'list')
            ->has('page.blocks.2.items', 4));
    }

    #[Test]
    public function помощь_с_вопросами_и_разметкой_для_поисковика(): void
    {
        $response = $this->get('/help')->assertInertia(fn (AssertableInertia $page) => $page
            ->has('faq', 5)
            ->where('faq.0.question', 'Сколько стоит разместить объявление?'));

        $this->assertStringContainsString('FAQPage', (string) $response->getContent());
    }

    #[Test]
    public function свой_текст_языка_из_админки(): void
    {
        $this->get('/uz/rules')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('page.title', 'Joylashtirish qoidalari'));

        Page::query()->where('key', 'rules')->update(['title_i18n' => json_encode(['uz' => 'Qoidalar'])]);

        $this->get('/uz/rules')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('page.title', 'Qoidalar')
            // Оглавление подписывает страницу её же заголовком
            ->where('nav', fn ($nav) => collect($nav)->contains('label', 'Qoidalar')));
    }

    #[Test]
    public function незаполненный_язык_уходит_в_машинный_перевод(): void
    {
        $rules = Page::query()->where('key', 'rules')->firstOrFail();
        $rules->update(['body' => "## Главное\n\n- Честные цены", 'body_i18n' => null]);

        DB::table('content_translations')->insert([
            ['hash' => sha1('Главное'), 'locale' => 'en', 'source' => 'Главное', 'translation' => 'The main thing', 'attempts' => 1, 'created_at' => now(), 'updated_at' => now()],
        ]);

        $this->get('/en/rules')->assertInertia(fn (AssertableInertia $page) => $page
            // Разметка — из русского текста, переведена каждая строка
            ->where('page.blocks.0', ['type' => 'heading', 'text' => 'The main thing'])
            // Перевода ещё нет — пока русский, а строка встала в очередь
            ->where('page.blocks.1.items.0', 'Честные цены'));

        $this->assertDatabaseHas('content_translations', ['locale' => 'en', 'source' => 'Честные цены']);
    }

    #[Test]
    public function вопрос_без_своего_перевода_тоже_переводится_машиной(): void
    {
        FaqItem::query()->orderBy('sort')->firstOrFail()->update(['question_i18n' => null]);

        $this->get('/tr/help')->assertOk();

        $this->assertDatabaseHas('content_translations', [
            'locale' => 'tr', 'source' => 'Сколько стоит разместить объявление?',
        ]);
    }

    #[Test]
    public function скрытая_страница_не_открывается_и_пропадает_из_оглавления(): void
    {
        Page::query()->where('key', 'guide')->update(['is_published' => false]);

        $this->get('/guide')->assertNotFound();
        $this->get('/about')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('nav', fn ($nav) => ! collect($nav)->contains('key', 'guide')));
        $this->get('/sitemap-static.xml')->assertDontSee('/guide');
    }

    #[Test]
    public function о_компании_из_базы(): void
    {
        Page::query()->where('key', 'about')->update(['excerpt' => 'Новый подзаголовок']);
        Page::query()->where('key', 'contacts')->update(['excerpt' => 'Пишите в любое время']);

        $this->get('/about')->assertInertia(fn (AssertableInertia $page) => $page
            ->component('About')
            ->where('page.title', 'О компании')
            ->where('page.lead', 'Новый подзаголовок')
            ->where('page.blocks.0.type', 'text')
            ->where('contacts.lead', 'Пишите в любое время')
            // Текст раздела «Офис на карте»
            ->where('contacts.blocks.0.text', fn (string $text) => str_starts_with($text, 'Приезжайте'))
            ->where('nav', fn ($nav) => collect($nav)->pluck('href')->all() === ['/about', '/about#contacts', '/help', '/guide', '/rules']));
    }

    /** Счётчик объявлений на «О компании» был вписан нулём, хотя сервер его считает. */
    #[Test]
    public function счётчик_объявлений_не_ноль_из_вёрстки(): void
    {
        $this->get('/about')->assertInertia(fn (AssertableInertia $page) => $page->has('stats.listings'));

        $about = (string) file_get_contents(resource_path('js/pages/About.tsx'));
        $this->assertStringContainsString('{stats.listings}', $about);
        $this->assertStringNotContainsString('<div className="t-num">0</div>', $about);
    }

    #[Test]
    public function подвал_ведёт_на_новые_адреса(): void
    {
        $footer = (string) file_get_contents(resource_path('js/components/SiteFooter.tsx'));

        $this->assertStringNotContainsString('#help', $footer);
        $this->assertStringContainsString('routes.help', $footer);
        $this->assertStringContainsString('routes.guide', $footer);
        $this->assertStringContainsString('routes.rules', $footer);
    }

    #[Test]
    public function пункт_меню_и_плашка_ведут_в_раздел_на_python(): void
    {
        $admin = fn (string $role) => User::factory()->create(['is_admin' => true, 'admin_role' => $role, 'status' => 'active']);
        $link = '/admin/python?next=/py/admin/site/page/';

        $this->actingAs($admin(AdminAccess::CONTENT_MANAGER));
        $this->get('/admin')->assertSee($link, false);
        Livewire::test(ContentDrafts::class)->assertSeeHtml(e($link.urlencode('?is_published__exact=0')));

        $this->actingAs($admin(AdminAccess::SALES));
        $this->get('/admin')->assertDontSee($link, false);
    }
}
