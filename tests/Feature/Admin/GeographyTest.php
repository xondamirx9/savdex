<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Exceptions\RecordIsReferenced;
use App\Models\City;
use App\Models\Company;
use App\Models\Country;
use App\Models\User;
use App\Support\AdminAccess;
use Database\Seeders\GeoSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Справочники географии в админке.
 *
 * До них список стран правился только сидером, то есть деплоем: новое
 * направление работы ждало разработчика. Теперь страну и город заводят
 * из панели, и она же не даёт снести страну, на которой стоят компании.
 *
 * Страны и города с этапа 2 переноса правятся в разделе на Python
 * (python/savdex/geo/admin.py, проверки — python/tests/test_countries_admin.py
 * и test_cities_admin.py). Здесь остались правила моделей и пункты меню,
 * которые туда ведут.
 */
class GeographyTest extends TestCase
{
    use RefreshDatabase;

    /** Пункт меню «Страны» — вход в раздел на Python через пропуск. */
    private const COUNTRIES_LINK = '/admin/python?next=/py/admin/geo/country/';

    /** Пункт меню «Города» — туда же. */
    private const CITIES_LINK = '/admin/python?next=/py/admin/geo/city/';

    private function admin(string $role): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => $role,
            'status' => 'active',
        ]);
    }

    private function country(string $code, bool $active = true): Country
    {
        $country = Country::query()->create([
            'code' => $code,
            'phone_code' => '+000',
            'currency_code' => 'XXX',
            'is_active' => $active,
        ]);

        $country->translations()->create(['locale' => 'ru', 'name' => "Страна {$code}"]);

        return $country->fresh();
    }

    // ── Доступ ──────────────────────────────────────────────────────

    #[Test]
    public function суперадмин_и_администратор_видят_справочники(): void
    {
        foreach ([AdminAccess::SUPERADMIN, AdminAccess::ADMIN] as $role) {
            $this->actingAs($this->admin($role));

            $this->get('/admin')
                ->assertSee(self::COUNTRIES_LINK, false)
                ->assertSee(self::CITIES_LINK, false);
        }
    }

    /** У продавца и финансиста раздела «Справочники» нет вовсе. */
    #[Test]
    public function роли_без_справочников_не_видят_страны(): void
    {
        foreach ([AdminAccess::SALES, AdminAccess::FINANCE, AdminAccess::SUPPORT] as $role) {
            $this->actingAs($this->admin($role));

            $this->get('/admin')
                ->assertDontSee(self::COUNTRIES_LINK, false)
                ->assertDontSee(self::CITIES_LINK, false);
        }
    }

    /**
     * Модератору справочники выданы только на чтение — пункты меню он
     * видит, а запрет правки проверяется на стороне Python.
     */
    #[Test]
    public function модератор_видит_справочники(): void
    {
        $this->actingAs($this->admin(AdminAccess::MODERATOR));

        $this->get('/admin')
            ->assertSee(self::COUNTRIES_LINK, false)
            ->assertSee(self::CITIES_LINK, false);
    }

    // ── Заведение страны ────────────────────────────────────────────

    #[Test]
    public function заведённая_страна_появляется_при_регистрации(): void
    {
        $this->actingAs($this->admin(AdminAccess::ADMIN));

        $this->country('kg');

        $shown = Country::query()->where('is_active', true)->with('translations')->get();

        $this->assertTrue(
            $shown->contains(fn (Country $c): bool => $c->code === 'kg'),
            'новая страна обязана попадать в список выбора при регистрации',
        );
    }

    /** Код страны приводится к нижнему регистру: иначе в списке два «Узбекистана». */
    #[Test]
    public function код_страны_приводится_к_нижнему_регистру(): void
    {
        $country = Country::query()->create([
            'code' => 'KG',
            'phone_code' => '+996',
            'currency_code' => 'KGS',
        ]);

        $this->assertSame('kg', $country->fresh()->code);
    }

    // ── Запрет удаления ─────────────────────────────────────────────

    #[Test]
    public function страна_с_компаниями_не_удаляется(): void
    {
        $country = $this->country('uz');
        Company::factory()->create(['country_id' => $country->id]);

        $this->assertTrue($country->isReferenced());

        try {
            $country->delete();
            $this->fail('страна с компаниями удалилась — защита не сработала');
        } catch (RecordIsReferenced $e) {
            $this->assertArrayHasKey('компании', $e->references);
        }

        $this->assertDatabaseHas('countries', ['id' => $country->id]);
    }

    /** Города уходят каскадом, поэтому считаются наравне с компаниями. */
    #[Test]
    public function страна_с_городами_не_удаляется(): void
    {
        $country = $this->country('uz');
        City::query()->create(['country_id' => $country->id, 'slug' => 'tashkent']);

        try {
            $country->delete();
            $this->fail('страна с городами удалилась — города ушли бы каскадом');
        } catch (RecordIsReferenced $e) {
            $this->assertArrayHasKey('города', $e->references);
        }

        $this->assertDatabaseHas('cities', ['slug' => 'tashkent']);
    }

    /** Резюме тоже держат страну: раньше удаление молча обнуляло её у них. */
    #[Test]
    public function страна_с_резюме_не_удаляется(): void
    {
        $country = $this->country('tj');
        $user = User::factory()->create();
        DB::table('resumes')->insert([
            'user_id' => $user->id, 'title' => 'Инженер', 'country_id' => $country->id,
            'created_at' => now(), 'updated_at' => now(),
        ]);

        try {
            $country->delete();
            $this->fail('страна с резюме удалилась — у резюме страна обнулилась бы');
        } catch (RecordIsReferenced $e) {
            $this->assertSame(['резюме' => 1], $e->references);
        }

        $this->assertDatabaseHas('resumes', ['country_id' => $country->id]);
    }

    #[Test]
    public function город_с_компаниями_не_удаляется(): void
    {
        $country = $this->country('uz');
        $city = City::query()->create(['country_id' => $country->id, 'slug' => 'tashkent']);
        Company::factory()->create(['country_id' => $country->id, 'city_id' => $city->id]);

        try {
            $city->delete();
            $this->fail('город с компаниями удалился — у них обнулился бы адрес');
        } catch (RecordIsReferenced $e) {
            $this->assertArrayHasKey('компании', $e->references);
        }

        $this->assertDatabaseHas('cities', ['id' => $city->id]);
    }

    /** Резюме держат город так же, как компании: иначе у них обнулился бы город. */
    #[Test]
    public function город_с_резюме_не_удаляется(): void
    {
        $country = $this->country('uz');
        $city = City::query()->create(['country_id' => $country->id, 'slug' => 'samarkand']);
        $user = User::factory()->create();
        DB::table('resumes')->insert([
            'user_id' => $user->id, 'title' => 'Инженер', 'city_id' => $city->id,
            'created_at' => now(), 'updated_at' => now(),
        ]);

        try {
            $city->delete();
            $this->fail('город с резюме удалился — у резюме город обнулился бы');
        } catch (RecordIsReferenced $e) {
            $this->assertSame(['резюме' => 1], $e->references);
        }

        $this->assertDatabaseHas('resumes', ['city_id' => $city->id]);
    }

    /** Ошибочно заведённую запись надо уметь убрать — иначе мусор навсегда. */
    #[Test]
    public function пустая_страна_удаляется(): void
    {
        $country = $this->country('zz');

        $this->assertFalse($country->isReferenced());

        $country->delete();

        $this->assertDatabaseMissing('countries', ['code' => 'zz']);
    }

    #[Test]
    public function пустой_город_удаляется(): void
    {
        $country = $this->country('uz');
        $city = City::query()->create(['country_id' => $country->id, 'slug' => 'nowhere']);

        $city->delete();

        $this->assertDatabaseMissing('cities', ['slug' => 'nowhere']);
    }

    /** Выключение — та замена удалению, которую предлагает подсказка. */
    #[Test]
    public function выключенная_страна_исчезает_из_выбора_но_остаётся_у_компаний(): void
    {
        $country = $this->country('uz');
        $company = Company::factory()->create(['country_id' => $country->id]);

        $country->update(['is_active' => false]);

        $this->assertFalse(
            Country::query()->where('is_active', true)->pluck('id')->contains($country->id),
            'выключенная страна не должна предлагаться при регистрации',
        );

        $this->assertSame($country->id, $company->fresh()->country_id, 'у компании страна обязана остаться');
    }

    /**
     * Деплой не откатывает правки стран.
     *
     * GeoSeeder гоняется на каждом деплое и раньше перезаписывал
     * существующие страны: выключенная в админке страна включалась
     * обратно, переименованная — возвращала старое имя. Теперь он
     * только досоздаёт недостающие.
     */
    #[Test]
    public function сидер_не_откатывает_правки_стран(): void
    {
        $this->seed(GeoSeeder::class);

        $uz = Country::query()->where('code', 'uz')->firstOrFail();
        $uz->update(['is_active' => false, 'sort' => 42]);
        $uz->translations()->where('locale', 'ru')->update(['name' => 'Республика Узбекистан']);
        $count = Country::count();

        $this->seed(GeoSeeder::class);

        $uz->refresh()->load('translations');
        $this->assertFalse($uz->is_active);
        $this->assertSame(42, $uz->sort);
        $this->assertSame('Республика Узбекистан', $uz->name('ru'));
        $this->assertSame($count, Country::count(), 'дублей нет');
    }

    /** То же для городов: порядок, «показывать», координаты и названия переживают деплой. */
    #[Test]
    public function сидер_не_откатывает_правки_городов(): void
    {
        $this->seed(GeoSeeder::class);

        $city = City::query()->where('slug', 'tashkent')->firstOrFail();
        $city->update(['is_active' => false, 'sort' => 42, 'lat' => 41.5]);
        $city->translations()->where('locale', 'ru')->update(['name' => 'Столица']);
        $count = City::count();

        $this->seed(GeoSeeder::class);

        $city->refresh()->load('translations');
        $this->assertFalse($city->is_active);
        $this->assertSame(42, $city->sort);
        $this->assertEqualsWithDelta(41.5, (float) $city->lat, 0.0000001);
        $this->assertSame('Столица', $city->name('ru'));
        $this->assertSame($count, City::count(), 'дублей нет');
    }

    /** На свежей базе сидер по-прежнему заводит страны со всеми названиями. */
    #[Test]
    public function сидер_заводит_страны_на_свежей_базе(): void
    {
        $this->seed(GeoSeeder::class);

        $uz = Country::query()->where('code', 'uz')->with('translations')->firstOrFail();

        $this->assertTrue($uz->is_active);
        $this->assertSame('Узбекистан', $uz->name('ru'));
        $this->assertCount(5, $uz->translations);
        $this->assertGreaterThan(0, $uz->cities()->count());
    }
}
