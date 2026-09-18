<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Company;
use App\Models\Country;
use Database\Seeders\GeoSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Collection;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * География площадки: 33 страны на пяти языках.
 *
 * Страна появляется на сайте одним движением — строкой в сидере,
 * который запускается на каждом деплое. Отдельного раздела в админке
 * у справочника нет, поэтому сидер обязан быть идемпотентным: второй
 * запуск не должен ни плодить дубли, ни терять переводы.
 */
class CountryListTest extends TestCase
{
    use RefreshDatabase;

    /** Страны, добавленные последними: их не было до расширения географии. */
    private const ADDED = [
        'md', 'lt', 'lv', 'sa', 'om', 'il', 'jo', 'iq', 'qa', 'kw', 'bh', 'eg',
        'lb', 'bg', 'hu', 'pl', 'ro', 'rs', 'sk', 'si', 'ua', 'hr', 'cz', 'ee',
    ];

    /** Страны, ради которых площадка делается: они были и остаются. */
    private const CORE = ['uz', 'kz', 'kg', 'tj', 'cn', 'tr', 'ru', 'ae', 'in'];

    protected function setUp(): void
    {
        parent::setUp();

        $this->seed(GeoSeeder::class);
    }

    #[Test]
    public function все_страны_заведены(): void
    {
        $codes = Country::query()->where('is_active', true)->pluck('code')->all();

        foreach ([...self::CORE, ...self::ADDED] as $code) {
            $this->assertContains($code, $codes, "страны «{$code}» нет в справочнике");
        }

        $this->assertCount(count(self::CORE) + count(self::ADDED), $codes);
    }

    /**
     * Название нужно на всех пяти языках.
     *
     * Откат на русский в name() есть, но он прячет пропажу: страна
     * молча показывалась бы по-русски среди китайских названий,
     * и заметить это можно только открыв китайскую версию.
     */
    #[Test]
    public function у_каждой_страны_название_на_пяти_языках(): void
    {
        foreach (Country::with('translations')->get() as $country) {
            foreach (['ru', 'uz', 'en', 'zh', 'tr'] as $locale) {
                $name = $country->translations->firstWhere('locale', $locale)?->name;

                $this->assertNotEmpty($name, "у «{$country->code}» нет названия на «{$locale}»");
            }

            // Узбекский — латиницей: кириллическое название выдаёт
            // забытый перевод, скопированный из русской колонки
            $this->assertDoesNotMatchRegularExpression(
                '/\p{Cyrillic}/u',
                (string) $country->translations->firstWhere('locale', 'uz')?->name,
                "узбекское название «{$country->code}» написано кириллицей",
            );
        }
    }

    #[Test]
    public function повторный_запуск_не_плодит_дублей(): void
    {
        $before = Country::count();

        $this->seed(GeoSeeder::class);

        $this->assertSame($before, Country::count());
        $this->assertSame(
            $before * 5,
            Country::query()->withCount('translations')->get()->sum('translations_count'),
        );
    }

    /**
     * Порядок: основные рынки сверху, остальные по алфавиту языка.
     *
     * Три десятка стран в порядке добавления в базу — это список,
     * в котором свою страну ищут глазами сверху вниз.
     */
    #[Test]
    public function основные_рынки_сверху_остальные_по_алфавиту(): void
    {
        $listed = Country::listed('ru');

        $this->assertSame(self::CORE, $listed->take(9)->pluck('code')->all());

        $tail = $listed->skip(9)->map(fn (Country $c): string => $c->name('ru'))->values()->all();
        $sorted = $tail;
        (new \Collator('ru'))->sort($sorted);

        $this->assertSame($sorted, $tail);
        $this->assertSame('Бахрейн', $tail[0]);
    }

    /** На английской версии алфавит английский. */
    #[Test]
    public function на_другом_языке_порядок_свой(): void
    {
        $names = Country::listed('en')->skip(9)->map(fn (Country $c): string => $c->name('en'))->values()->all();

        $this->assertSame('Bahrain', $names[0]);
        $this->assertSame('Ukraine', $names[count($names) - 1]);
    }

    /** Новая страна доезжает до витрины: справочник и выбор при регистрации. */
    #[Test]
    public function новые_страны_видны_на_сайте(): void
    {
        $this->get('/countries')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('planned', fn (Collection $planned): bool => $planned
                    ->pluck('code')
                    ->intersect(self::ADDED)
                    ->count() === count(self::ADDED)));

        $this->get('/en/countries')
            ->assertOk()
            ->assertSee('Saudi Arabia');
    }

    /** Страна с компаниями уходит из «в работе» в действующие. */
    #[Test]
    public function страна_с_компанией_становится_действующей(): void
    {
        Company::factory()->create([
            'status' => Company::STATUS_ACTIVE,
            'country_id' => Country::where('code', 'pl')->value('id'),
        ]);

        $this->get('/countries')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('countries.0.code', 'pl')
            ->where('countries.0.companies', 1)
            ->where('planned', fn (Collection $planned): bool => ! $planned
                ->pluck('code')
                ->contains('pl')));
    }
}
