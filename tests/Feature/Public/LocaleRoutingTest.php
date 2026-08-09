<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Company;
use App\Models\Listing;
use App\Models\User;
use App\Support\Locales;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Язык в адресе.
 *
 * Раньше все пять языков жили на одном адресе и переключались через
 * сессию: поисковик видел одну страницу вместо пяти, а присланную
 * ссылку получатель открывал на своём языке, а не на языке отправителя.
 */
class LocaleRoutingTest extends TestCase
{
    use RefreshDatabase;

    /** @return list<array{string}> */
    public static function языки(): array
    {
        return [['uz'], ['en'], ['zh'], ['tr']];
    }

    #[Test]
    #[DataProvider('языки')]
    public function страница_открывается_по_адресу_с_языком(string $locale): void
    {
        $this->get("/{$locale}/catalog")->assertOk();
        $this->assertSame($locale, app()->getLocale());
    }

    #[Test]
    public function адрес_без_префикса_остаётся_русским(): void
    {
        $this->get('/catalog')->assertOk();

        $this->assertSame('ru', app()->getLocale());
    }

    /** «/uz» без хвоста — это главная, а не пустой адрес. */
    #[Test]
    public function главная_на_языке_открывается_коротким_адресом(): void
    {
        $this->get('/uz')->assertOk();
        $this->assertSame('uz', app()->getLocale());
    }

    #[Test]
    public function неизвестный_язык_не_считается_префиксом(): void
    {
        // «/de/catalog» — не немецкая версия каталога, а несуществующий адрес
        $this->get('/de/catalog')->assertNotFound();
    }

    #[Test]
    public function карточка_объявления_открывается_на_каждом_языке(): void
    {
        $listing = Listing::factory()->create([
            'status' => Listing::STATUS_ACTIVE,
            'published_at' => now()->subDay(),
        ]);

        foreach (Locales::codes() as $locale) {
            $this->get(Locales::url("/listing/{$listing->slug}", $locale))->assertOk();
        }
    }

    // ── Запоминание выбора ───────────────────────────────────

    #[Test]
    public function переход_по_ссылке_с_языком_запоминает_выбор(): void
    {
        $this->get('/uz/catalog')->assertOk();

        // Дальше человек ходит по площадке без префикса — и всё равно
        // должен остаться на узбекском
        $this->get('/catalog')->assertRedirect(url('/uz/catalog'));
    }

    #[Test]
    public function язык_из_адреса_сохраняется_в_профиль(): void
    {
        $user = User::factory()->create(['locale' => 'ru']);

        $this->actingAs($user)->get('/en/catalog')->assertOk();

        $this->assertSame('en', $user->fresh()->locale);
    }

    /**
     * Робот приходит без сессии и профиля — и остаётся на русской
     * версии. Иначе он получал бы редирект на язык предыдущего
     * посетителя и индексировал не то, что запрашивал.
     */
    #[Test]
    public function робот_не_перенаправляется(): void
    {
        $this->get('/catalog')->assertOk();
    }

    #[Test]
    public function служебные_адреса_не_перенаправляются(): void
    {
        $this->withSession(['locale' => 'uz']);

        $this->get('/robots.txt')->assertOk();
        $this->get('/sitemap.xml')->assertOk();
    }

    // ── Переключатель ────────────────────────────────────────

    #[Test]
    public function переключение_возвращает_на_ту_же_страницу_на_другом_языке(): void
    {
        $this->from(url('/uz/catalog'))
            ->post('/locale/en')
            ->assertRedirect(url('/en/catalog'));
    }

    /** Обратный переход на русский: у русского адреса префикса нет. */
    #[Test]
    public function переключение_на_русский_убирает_префикс(): void
    {
        $this->from(url('/uz/catalog'))
            ->post('/uz/locale/ru')
            ->assertRedirect(url('/catalog'));
    }

    #[Test]
    public function неизвестный_язык_в_переключателе_отдаёт_404(): void
    {
        $this->post('/locale/de')->assertNotFound();
    }

    // ── Формы и перенаправления ──────────────────────────────

    /**
     * Отправка формы из версии на другом языке не должна выбрасывать
     * человека на русскую страницу.
     */
    #[Test]
    public function перенаправление_после_формы_сохраняет_язык(): void
    {
        $user = User::factory()->for(Company::factory())->create(['locale' => 'uz']);

        $this->actingAs($user)
            ->post('/uz/logout')
            ->assertRedirect(url('/uz'));
    }

    #[Test]
    public function вход_из_версии_на_другом_языке_ведёт_в_кабинет_на_нём_же(): void
    {
        $user = User::factory()->for(Company::factory())->create([
            'locale' => 'ru',
            'password' => bcrypt('secret-pass-1'),
        ]);

        $this->post('/en/login', ['email' => $user->email, 'password' => 'secret-pass-1'])
            ->assertRedirect(url('/en/cabinet'));
    }

    // ── Сборка адресов ───────────────────────────────────────

    #[Test]
    public function адрес_собирается_с_нужным_языком(): void
    {
        $this->assertSame(url('/catalog'), Locales::url('/catalog', 'ru'));
        $this->assertSame(url('/uz/catalog'), Locales::url('/catalog', 'uz'));
        // Чужой префикс снимается, иначе адреса склеивались бы в «/uz/en/»
        $this->assertSame(url('/en/catalog'), Locales::url('/uz/catalog', 'en'));
        $this->assertSame(url('/uz'), Locales::url('/', 'uz'));
        $this->assertSame(url('/uz/catalog?q=цемент'), Locales::url('/catalog?q=цемент', 'uz'));
    }
}
