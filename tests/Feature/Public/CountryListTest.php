<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\City;
use App\Models\Company;
use App\Models\Country;
use App\Models\User;
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

    /**
     * Границы стран для проверки координат.
     *
     * Широкие рамки с запасом: задача не в том, чтобы поймать сдвиг
     * на километр, а в том, чтобы поймать перепутанные местами широту
     * и долготу и город, приписанный не к той стране. Обе ошибки
     * всплыли бы уже на карте поставщиков.
     *
     * [минимальная широта, максимальная, минимальная долгота, максимальная]
     */
    private const BOUNDS = [
        'uz' => [37.0, 45.7, 55.9, 73.2],
        'kz' => [40.5, 55.5, 46.4, 87.4],
        'kg' => [39.1, 43.3, 69.2, 80.3],
        'tj' => [36.6, 41.1, 67.3, 75.2],
        'cn' => [18.0, 53.6, 73.4, 135.1],
        'tr' => [35.8, 42.2, 25.6, 44.9],
        'ru' => [41.1, 77.0, 19.0, 180.0],
        'ae' => [22.6, 26.1, 51.5, 56.4],
        'in' => [6.7, 35.7, 68.1, 97.4],
        'sa' => [16.3, 32.2, 34.4, 55.7],
        'qa' => [24.4, 26.2, 50.7, 51.7],
        'kw' => [28.5, 30.1, 46.5, 48.5],
        'bh' => [25.7, 26.4, 50.3, 50.8],
        'om' => [16.6, 26.5, 51.9, 59.9],
        'iq' => [29.0, 37.4, 38.8, 48.6],
        'jo' => [29.1, 33.4, 34.9, 39.3],
        'lb' => [33.0, 34.7, 35.1, 36.7],
        'il' => [29.4, 33.4, 34.2, 35.9],
        'eg' => [21.9, 31.7, 24.6, 36.9],
        'pl' => [49.0, 54.9, 14.1, 24.2],
        'cz' => [48.5, 51.1, 12.0, 18.9],
        'sk' => [47.7, 49.7, 16.8, 22.6],
        'hu' => [45.7, 48.6, 16.1, 22.9],
        'ro' => [43.6, 48.3, 20.2, 29.7],
        'bg' => [41.2, 44.3, 22.3, 28.7],
        'rs' => [42.2, 46.2, 18.8, 23.1],
        'hr' => [42.3, 46.6, 13.4, 19.5],
        'si' => [45.4, 46.9, 13.3, 16.6],
        'ua' => [44.3, 52.4, 22.1, 40.3],
        'md' => [45.4, 48.5, 26.6, 30.2],
        'lt' => [53.8, 56.5, 20.9, 26.9],
        'lv' => [55.6, 58.1, 20.9, 28.3],
        'ee' => [57.5, 59.7, 21.7, 28.2],
    ];

    /** Пустая страна в списке — тупик: выбрать город в ней нельзя. */
    #[Test]
    public function у_каждой_страны_есть_города(): void
    {
        foreach (Country::withCount('cities')->get() as $country) {
            $this->assertGreaterThan(0, $country->cities_count, "у страны «{$country->code}» нет городов");
        }
    }

    #[Test]
    public function координаты_города_попадают_в_свою_страну(): void
    {
        foreach (City::with('country')->get() as $city) {
            $code = $city->country->code;
            [$latMin, $latMax, $lngMin, $lngMax] = self::BOUNDS[$code];

            $this->assertNotNull($city->lat, "у города «{$city->slug}» нет координат");

            $this->assertTrue(
                (float) $city->lat >= $latMin && (float) $city->lat <= $latMax
                && (float) $city->lng >= $lngMin && (float) $city->lng <= $lngMax,
                "город «{$city->slug}» с координатами {$city->lat}, {$city->lng} лежит вне «{$code}»",
            );
        }
    }

    #[Test]
    public function у_каждого_города_название_на_пяти_языках(): void
    {
        foreach (City::with('translations')->get() as $city) {
            foreach (['ru', 'uz', 'en', 'zh', 'tr'] as $locale) {
                $name = $city->translations->firstWhere('locale', $locale)?->name;

                $this->assertNotEmpty($name, "у города «{$city->slug}» нет названия на «{$locale}»");
            }

            $this->assertDoesNotMatchRegularExpression(
                '/\p{Cyrillic}/u',
                (string) $city->translations->firstWhere('locale', 'uz')?->name,
                "узбекское название «{$city->slug}» написано кириллицей",
            );

            // slug уходит в адреса и в сопоставление при загрузке из книги
            $this->assertMatchesRegularExpression('/^[a-z0-9-]+$/', $city->slug);
        }
    }

    /**
     * Один и тот же slug в двух странах ломает загрузку из книги:
     * город там ищется по slug, и первый найденный забирает всё.
     */
    #[Test]
    public function slug_города_не_повторяется(): void
    {
        $slugs = City::pluck('slug');

        $this->assertSame(
            $slugs->count(),
            $slugs->unique()->count(),
            'повторяются: '.$slugs->duplicates()->implode(', '),
        );
    }

    #[Test]
    public function повторный_запуск_не_плодит_городов(): void
    {
        $before = City::count();

        $this->seed(GeoSeeder::class);

        $this->assertSame($before, City::count());
        $this->assertSame($before * 5, City::query()->withCount('translations')->get()->sum('translations_count'));
    }

    /** Города доезжают до формы регистрации — ради этого справочник и нужен. */
    #[Test]
    public function города_видны_при_регистрации_компании(): void
    {
        $user = User::factory()->create(['company_id' => null]);

        $poland = Country::where('code', 'pl')->value('id');

        $this->actingAs($user)->get('/onboarding/company')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('cities', fn (Collection $cities): bool => $cities
                    ->where('country_id', $poland)
                    ->pluck('name')
                    ->contains('Варшава')));
    }
}
