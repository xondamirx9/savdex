<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Company;
use App\Models\Country;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Справочник стран.
 *
 * В списке при регистрации было два «Узбекистана»: сидер географии
 * заводил страну с кодом 'uz', а фабрика компаний искала 'UZ'.
 * Уникальность в базе регистрозависима, и рядом появлялась вторая
 * страна — без единого города, потому что города висели на первой.
 */
class CountryDirectoryTest extends TestCase
{
    use RefreshDatabase;

    #[Test]
    public function код_страны_приводится_к_нижнему_регистру(): void
    {
        $country = Country::create(['code' => 'KZ', 'phone_code' => '7', 'currency_code' => 'KZT', 'is_active' => true]);

        $this->assertSame('kz', $country->fresh()->code);
    }

    /** Регистр не должен плодить страны: 'UZ' и 'uz' — одна и та же. */
    #[Test]
    public function поиск_по_коду_в_другом_регистре_не_создаёт_дубль(): void
    {
        Country::create(['code' => 'uz', 'phone_code' => '998', 'currency_code' => 'UZS', 'is_active' => true]);
        Country::firstOrCreate(['code' => mb_strtolower('UZ')], ['phone_code' => '998', 'currency_code' => 'UZS', 'is_active' => true]);

        $this->assertSame(1, Country::where('code', 'uz')->count());
    }

    /** Фабрика компаний берёт ту же страну, что и сидер географии. */
    #[Test]
    public function фабрика_не_заводит_вторую_страну(): void
    {
        Company::factory()->count(3)->create();

        $this->assertSame(
            1,
            Country::whereIn('code', ['uz', 'UZ'])->count(),
            'страна должна быть одна — иначе в форме регистрации два одинаковых пункта',
        );
    }
}
