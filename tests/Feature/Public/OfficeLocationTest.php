<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Setting;
use App\Support\OfficeLocation;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Офис на карте на странице «О компании».
 *
 * Адрес и координаты живут в настройках площадки, а не в вёрстке:
 * переезд офиса не должен требовать деплоя. Проверяется вся дорога —
 * от строки в админке до данных, с которыми страница уходит в браузер.
 */
class OfficeLocationTest extends TestCase
{
    use RefreshDatabase;

    private function setting(string $key, mixed $value, string $type = 'string'): void
    {
        Setting::updateOrCreate(
            ['key' => $key],
            ['group' => 'contacts', 'label' => $key, 'type' => $type, 'value' => $value],
        );
    }

    private function office(string $address = 'г. Ташкент, ул. Амира Темура, 1', string $coords = '41.311081, 69.240562'): void
    {
        $this->setting(OfficeLocation::KEY_ADDRESS, $address, 'text');
        $this->setting(OfficeLocation::KEY_COORDS, $coords);
    }

    // ── Страница ─────────────────────────────────────────────

    #[Test]
    public function адрес_и_координаты_приходят_на_страницу_из_настроек(): void
    {
        $this->office();

        $this->get('/about')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('office.address', 'г. Ташкент, ул. Амира Темура, 1')
            ->where('office.lat', 41.311081)
            ->where('office.lng', 69.240562),
        );
    }

    /** Смена настройки видна на витрине сразу — иначе правка выглядит несохранившейся. */
    #[Test]
    public function правка_настройки_меняет_адрес_на_странице(): void
    {
        $this->office();
        $this->get('/about');

        $this->setting(OfficeLocation::KEY_ADDRESS, 'г. Самарканд, ул. Регистан, 5', 'text');

        $this->get('/about')->assertInertia(
            fn (AssertableInertia $page) => $page->where('office.address', 'г. Самарканд, ул. Регистан, 5'),
        );
    }

    /** Пустые настройки — свежая установка: раздела «Офис» на странице просто нет. */
    #[Test]
    public function без_настроек_раздела_офиса_нет(): void
    {
        $this->get('/about')->assertInertia(fn (AssertableInertia $page) => $page->where('office', null));
    }

    /**
     * Адрес без координат — рабочий случай: здание бывает в адресном
     * справочнике, но не на карте. Раздел показывается без карты.
     */
    #[Test]
    public function адрес_без_координат_показывается_без_карты(): void
    {
        $this->setting(OfficeLocation::KEY_ADDRESS, 'г. Ташкент, Мирзо-Улугбекский р-н', 'text');

        $this->get('/about')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('office.address', 'г. Ташкент, Мирзо-Улугбекский р-н')
            ->where('office.lat', null)
            ->where('office.lng', null),
        );
    }

    /** Опечатка в координатах не должна ронять публичную страницу. */
    #[Test]
    public function испорченные_координаты_не_ломают_страницу(): void
    {
        $this->office(coords: '41,31 69,24');

        $this->get('/about')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page->where('office.lat', null));
    }

    #[Test]
    public function масштаб_карты_берётся_из_настроек(): void
    {
        $this->office();
        $this->setting(OfficeLocation::KEY_ZOOM, 12, 'number');

        $this->get('/about')->assertInertia(fn (AssertableInertia $page) => $page->where('office.zoom', 12));
    }

    /** Масштаб вне диапазона тайлов OpenStreetMap даёт серую заливку вместо карты. */
    #[Test]
    public function масштаб_вне_диапазона_прижимается_к_границе(): void
    {
        $this->office();
        $this->setting(OfficeLocation::KEY_ZOOM, 40, 'number');

        $this->get('/about')->assertInertia(fn (AssertableInertia $page) => $page->where('office.zoom', 19));
    }

    /** Адрес офиса размечается для поисковика — он попадает в карточку организации в выдаче. */
    #[Test]
    public function адрес_попадает_в_разметку_для_поисковика(): void
    {
        $this->office();

        $html = (string) $this->get('/about')->getContent();

        $this->assertStringContainsString('PostalAddress', $html);
        $this->assertStringContainsString('GeoCoordinates', $html);
    }

    #[Test]
    public function без_настроек_разметки_адреса_нет(): void
    {
        $this->assertStringNotContainsString('PostalAddress', (string) $this->get('/about')->getContent());
    }

    // ── Разбор координат ─────────────────────────────────────

    /** @return array<string, array{string, float|null, float|null}> */
    public static function строкиКоординат(): array
    {
        return [
            'запятая с пробелом' => ['41.311081, 69.240562', 41.311081, 69.240562],
            'запятая без пробела' => ['41.311081,69.240562', 41.311081, 69.240562],
            'пробелы по краям' => ['  41.311081 , 69.240562  ', 41.311081, 69.240562],
            'целые числа' => ['41, 69', 41.0, 69.0],
            'южное полушарие' => ['-33.865143, 151.2099', -33.865143, 151.2099],
            'пусто' => ['', null, null],
            'запятая как разделитель дробной части' => ['41,31 69,24', null, null],
            'одно число' => ['41.311081', null, null],
            'широта больше 90' => ['95.0, 69.240562', null, null],
            'долгота больше 180' => ['41.311081, 200.5', null, null],
            'текст вместо чисел' => ['Ташкент', null, null],
        ];
    }

    #[Test]
    #[DataProvider('строкиКоординат')]
    public function координаты_разбираются(string $raw, ?float $lat, ?float $lng): void
    {
        $this->assertSame([$lat, $lng], OfficeLocation::coords($raw));
    }
}
