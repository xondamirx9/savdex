<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Company;
use App\Models\Listing;
use App\Models\Setting;
use App\Support\CurrencyRate;
use App\Support\PriceDisplay;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\Http;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Цена в валюте языка.
 *
 * Продавец назначает цену в своей валюте, витрина рядом показывает
 * приблизительный пересчёт в валюту языка по курсу ЦБ: английская
 * версия — доллары, китайская — юани. Валюта языка задаётся
 * в настройках. Пересчёта нет, когда валюты совпадают или курса нет.
 */
class PriceDisplayTest extends TestCase
{
    use RefreshDatabase;

    private Company $company;

    protected function setUp(): void
    {
        parent::setUp();

        $this->company = Company::factory()->create(['status' => 'active']);
    }

    /**
     * Подмена таблицы ЦБ. Один раз на тест: Http::fake отвечает первой
     * подходящей заглушкой, и вторая подмена ничего бы не изменила.
     *
     * @param  array<string, array{Rate: string, Nominal?: string}>  $rates
     */
    private function fakeRates(array $rates = [
        'USD' => ['Rate' => '12800.00'],
        'EUR' => ['Rate' => '14900.00'],
        'CNY' => ['Rate' => '1780.50'],
        'TRY' => ['Rate' => '310.00'],
    ]): void
    {
        $rows = [];

        foreach ($rates as $code => $row) {
            $rows[] = ['Ccy' => $code, 'Rate' => $row['Rate'], 'Nominal' => $row['Nominal'] ?? '1'];
        }

        Http::fake(['cbu.uz/*' => Http::response($rows)]);
    }

    /** @param array<string, mixed> $overrides */
    private function listing(array $overrides = []): Listing
    {
        return Listing::factory()->create([
            'company_id' => $this->company->id,
            'status' => Listing::STATUS_ACTIVE,
            'price' => 1_250_000,
            'currency' => 'UZS',
            'price_negotiable' => false,
            ...$overrides,
        ]);
    }

    #[Test]
    public function на_каждом_языке_своя_валюта(): void
    {
        $this->fakeRates();
        $this->listing();

        // Русская версия первой: после «/en/…» сессия запоминает язык,
        // и адрес без префикса уводился бы редиректом
        $this->get('/catalog')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('listings.data.0.price', 1_250_000)
            ->where('listings.data.0.currency', 'UZS')
            ->where('listings.data.0.converted', null));

        $this->get('/uz/catalog')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('listings.data.0.converted', null));

        $this->get('/en/catalog')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('listings.data.0.price', 1_250_000)
            ->where('listings.data.0.currency', 'UZS')
            ->where('listings.data.0.converted', ['price' => 97.7, 'currency' => 'USD']));

        $this->get('/zh/catalog')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('listings.data.0.converted', ['price' => 702, 'currency' => 'CNY']));

        $this->get('/tr/catalog')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('listings.data.0.converted', ['price' => 4030, 'currency' => 'TRY']));
    }

    #[Test]
    public function долларовая_цена_на_русской_версии_пересчитывается_в_сумы(): void
    {
        $this->fakeRates();
        $this->listing(['price' => 95, 'currency' => 'USD']);

        $this->get('/catalog')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('listings.data.0.price', 95)
            ->where('listings.data.0.currency', 'USD')
            ->where('listings.data.0.converted', ['price' => 1_220_000, 'currency' => 'UZS']));
    }

    #[Test]
    public function валюта_языка_меняется_в_настройках(): void
    {
        $this->fakeRates();
        $this->listing();

        Setting::put(PriceDisplay::key('en'), 'EUR');

        $this->get('/en/catalog')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('listings.data.0.converted', ['price' => 83.9, 'currency' => 'EUR']));
    }

    #[Test]
    public function неизвестный_код_в_настройке_не_ломает_витрину(): void
    {
        $this->fakeRates();
        $this->listing();

        Setting::put(PriceDisplay::key('en'), 'XXX');

        $this->assertSame('USD', PriceDisplay::currency('en'));

        $this->get('/en/catalog')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('listings.data.0.converted', ['price' => 97.7, 'currency' => 'USD']));
    }

    #[Test]
    public function без_курса_показывается_только_цена_продавца(): void
    {
        $this->fakeRates(['USD' => ['Rate' => '12800.00']]);
        $this->listing();

        $this->get('/zh/catalog')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('listings.data.0.price', 1_250_000)
            ->where('listings.data.0.converted', null));
    }

    #[Test]
    public function при_недоступном_цб_витрина_без_пересчёта_а_касса_по_запасному_курсу(): void
    {
        Http::fake(['cbu.uz/*' => Http::response('', 500)]);
        $this->listing();

        $this->get('/en/catalog')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('listings.data.0.price', 1_250_000)
            ->where('listings.data.0.converted', null));

        $this->assertNull(app(CurrencyRate::class)->rate('USD'));
        $this->assertSame(12_800.0, app(CurrencyRate::class)->usd());
    }

    #[Test]
    public function при_недоступном_цб_берётся_последний_известный_курс(): void
    {
        Http::fake(['cbu.uz/*' => Http::response('', 500)]);
        Cache::put('cbu.rates.last', ['USD' => 12_500.0]);
        $this->listing();

        $this->get('/en/catalog')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('listings.data.0.converted', ['price' => 100, 'currency' => 'USD']));
    }

    #[Test]
    public function обновление_по_расписанию_кладёт_таблицу_в_кэш(): void
    {
        $this->fakeRates(['USD' => ['Rate' => '12600.00']]);

        $this->assertTrue(app(CurrencyRate::class)->refresh());
        $this->assertSame(['USD' => 12_600.0], Cache::get('cbu.rates'));
        $this->assertSame(['USD' => 12_600.0], Cache::get('cbu.rates.last'));
    }

    #[Test]
    public function сбой_обновления_не_трогает_таблицу(): void
    {
        Http::fake(['cbu.uz/*' => Http::response('', 500)]);
        Cache::put('cbu.rates', ['USD' => 12_600.0]);

        $this->assertFalse(app(CurrencyRate::class)->refresh());
        $this->assertSame(['USD' => 12_600.0], Cache::get('cbu.rates'));
        $this->assertSame(12_600.0, app(CurrencyRate::class)->usd());
    }

    #[Test]
    public function курс_доллара_запомненный_до_общей_таблицы_не_пропадает(): void
    {
        Http::fake(['cbu.uz/*' => Http::response('', 500)]);
        Cache::put('cbu.rate.usd.last', 12_500.0);

        $this->assertSame(12_500.0, app(CurrencyRate::class)->usd());
    }

    #[Test]
    public function меньше_копейки_не_показывается_как_ноль(): void
    {
        $this->fakeRates();
        $this->listing(['price' => 30]);

        $this->get('/en/catalog')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('listings.data.0.price', 30)
            ->where('listings.data.0.converted', null));
    }

    #[Test]
    public function договорная_цена_не_пересчитывается(): void
    {
        $this->fakeRates();
        $this->listing(['price' => 1_250_000, 'price_negotiable' => true]);

        $this->get('/en/catalog')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('listings.data.0.negotiable', true)
            ->where('listings.data.0.converted', null));
    }

    #[Test]
    public function страница_объявления_пересчитывает_цену_и_комплект(): void
    {
        $this->fakeRates();
        $listing = $this->listing(['bundle_price' => 12_500_000]);

        $this->get('/en/listing/'.$listing->slug)->assertInertia(fn (AssertableInertia $page) => $page
            ->where('listing.price', 1_250_000)
            ->where('listing.currency', 'UZS')
            ->where('listing.converted', ['price' => 97.7, 'currency' => 'USD'])
            ->where('listing.bundle_converted', ['price' => 977, 'currency' => 'USD']));
    }

    #[Test]
    public function курс_за_сто_единиц_делится_на_номинал(): void
    {
        $this->fakeRates(['JPY' => ['Rate' => '8500.00', 'Nominal' => '100']]);

        $this->assertEqualsWithDelta(85.0, app(CurrencyRate::class)->rate('JPY'), 0.001);
        $this->assertNull(app(CurrencyRate::class)->rate('CNY'));
        $this->assertSame(1.0, app(CurrencyRate::class)->rate('UZS'));
    }

    #[Test]
    public function курс_цб_запрашивается_один_раз(): void
    {
        $this->fakeRates();
        $this->listing();
        $this->listing(['price' => 95, 'currency' => 'USD']);

        $this->get('/en/catalog')->assertOk();

        Http::assertSentCount(1);
    }

    #[Test]
    public function округление_до_трёх_значащих_цифр_но_не_мельче_копеек(): void
    {
        $this->assertSame(97.7, PriceDisplay::round(97.66));
        $this->assertSame(0.74, PriceDisplay::round(0.7412));
        $this->assertSame(1_250_000.0, PriceDisplay::round(1_250_048.3));
        $this->assertSame(706.0, PriceDisplay::round(706.3));
        $this->assertSame(12.3, PriceDisplay::round(12.34));
        $this->assertSame(5.0, PriceDisplay::round(5));
        $this->assertSame(0.01, PriceDisplay::round(0.0123));
        $this->assertSame(0.0, PriceDisplay::round(0));
    }

    #[Test]
    public function настройки_валют_заведены_миграцией(): void
    {
        $this->assertSame(
            PriceDisplay::DEFAULTS,
            Setting::query()->where('group', 'currency')->orderBy('sort')->pluck('value', 'key')
                ->mapWithKeys(fn (mixed $v, string $k): array => [substr($k, strlen(PriceDisplay::KEY_PREFIX)) => $v])
                ->all(),
        );
    }
}
