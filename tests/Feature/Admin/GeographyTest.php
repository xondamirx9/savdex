<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Exceptions\RecordIsReferenced;
use App\Filament\Resources\Cities\CityResource;
use App\Filament\Resources\Cities\Pages\CreateCity;
use App\Filament\Resources\Cities\Pages\EditCity;
use App\Filament\Resources\Cities\Pages\ListCities;
use App\Filament\Resources\Countries\CountryResource;
use App\Filament\Resources\Countries\Pages\CreateCountry;
use App\Filament\Resources\Countries\Pages\EditCountry;
use App\Filament\Resources\Countries\Pages\ListCountries;
use App\Models\City;
use App\Models\Company;
use App\Models\Country;
use App\Models\User;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Справочники географии в админке.
 *
 * До них список стран правился только сидером, то есть деплоем: новое
 * направление работы ждало разработчика. Теперь страну и город заводят
 * из панели, и она же не даёт снести страну, на которой стоят компании.
 */
class GeographyTest extends TestCase
{
    use RefreshDatabase;

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

            $this->assertTrue(CountryResource::canViewAny(), "{$role} должен видеть страны");
            $this->assertTrue(CountryResource::canCreate(), "{$role} должен заводить страны");
            $this->assertTrue(CityResource::canViewAny(), "{$role} должен видеть города");
            $this->assertTrue(CityResource::canCreate(), "{$role} должен заводить города");
        }
    }

    /** У продавца и финансиста раздела «Справочники» нет вовсе. */
    #[Test]
    public function роли_без_справочников_не_видят_страны(): void
    {
        foreach ([AdminAccess::SALES, AdminAccess::FINANCE, AdminAccess::SUPPORT] as $role) {
            $this->actingAs($this->admin($role));

            $this->assertFalse(CountryResource::canViewAny(), "{$role} не должен видеть страны");
            $this->assertFalse(CityResource::canViewAny(), "{$role} не должен видеть города");
        }
    }

    /** Модератору справочники выданы только на чтение. */
    #[Test]
    public function модератор_смотрит_но_не_правит(): void
    {
        $this->actingAs($this->admin(AdminAccess::MODERATOR));

        $this->assertTrue(CountryResource::canViewAny());
        $this->assertFalse(CountryResource::canCreate());
        $this->assertFalse(CityResource::canCreate());
    }

    // ── Экраны ──────────────────────────────────────────────────────

    #[Test]
    public function списки_открываются_с_данными(): void
    {
        $this->actingAs($this->admin(AdminAccess::ADMIN));

        $uz = $this->country('uz');
        $city = City::query()->create(['country_id' => $uz->id, 'slug' => 'tashkent', 'is_active' => true]);
        $city->translations()->create(['locale' => 'ru', 'name' => 'Ташкент']);

        Livewire::test(ListCountries::class)
            ->assertOk()
            ->assertCanSeeTableRecords([$uz]);

        Livewire::test(ListCities::class)
            ->assertOk()
            ->assertCanSeeTableRecords([$city]);
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

    // ── Формы ───────────────────────────────────────────────────────

    /**
     * Форма заводится целиком, вместе с переводами.
     *
     * Список открывался и тогда, когда форма падала: в этом проекте
     * так уже было с финансовыми операциями. Поэтому здесь не «экран
     * открылся», а «страна создана и её видно».
     */
    #[Test]
    public function страна_заводится_через_форму_админки(): void
    {
        $this->actingAs($this->admin(AdminAccess::ADMIN));

        Livewire::test(CreateCountry::class)
            ->fillForm([
                'code' => 'kg',
                'phone_code' => '+996',
                'currency_code' => 'KGS',
                'sort' => 5,
                'is_active' => true,
                'translations' => [
                    ['locale' => 'ru', 'name' => 'Киргизия'],
                    ['locale' => 'en', 'name' => 'Kyrgyzstan'],
                ],
            ])
            ->call('create')
            ->assertHasNoFormErrors();

        $country = Country::query()->where('code', 'kg')->with('translations')->first();

        $this->assertNotNull($country, 'страна должна была создаться');
        $this->assertSame('Киргизия', $country->name('ru'));
        $this->assertSame('Kyrgyzstan', $country->name('en'));
        $this->assertSame('+996', $country->phone_code);
    }

    #[Test]
    public function город_заводится_через_форму_админки(): void
    {
        $this->actingAs($this->admin(AdminAccess::ADMIN));

        $country = $this->country('kg');

        Livewire::test(CreateCity::class)
            ->fillForm([
                'country_id' => $country->id,
                'slug' => 'bishkek',
                'sort' => 0,
                'is_active' => true,
                'translations' => [
                    ['locale' => 'ru', 'name' => 'Бишкек'],
                ],
            ])
            ->call('create')
            ->assertHasNoFormErrors();

        $city = City::query()->where('slug', 'bishkek')->with('translations')->first();

        $this->assertNotNull($city, 'город должен был создаться');
        $this->assertSame('Бишкек', $city->name('ru'));
        $this->assertSame($country->id, $city->country_id);
    }

    /** Экран правки обязан открываться на существующей записи. */
    #[Test]
    public function формы_правки_открываются(): void
    {
        $this->actingAs($this->admin(AdminAccess::ADMIN));

        $country = $this->country('uz');
        $city = City::query()->create(['country_id' => $country->id, 'slug' => 'tashkent']);
        $city->translations()->create(['locale' => 'ru', 'name' => 'Ташкент']);

        Livewire::test(EditCountry::class, ['record' => $country->getRouteKey()])
            ->assertOk()
            ->assertFormSet(['code' => 'uz']);

        Livewire::test(EditCity::class, ['record' => $city->getRouteKey()])
            ->assertOk()
            ->assertFormSet(['slug' => 'tashkent']);
    }

    /** Два кода страны в одном регистре — это один и тот же список выбора. */
    #[Test]
    public function повторный_код_страны_не_проходит(): void
    {
        $this->actingAs($this->admin(AdminAccess::ADMIN));

        $this->country('uz');

        Livewire::test(CreateCountry::class)
            ->fillForm([
                'code' => 'uz',
                'phone_code' => '+998',
                'currency_code' => 'UZS',
                'sort' => 0,
                'translations' => [['locale' => 'ru', 'name' => 'Дубль']],
            ])
            ->call('create')
            ->assertHasFormErrors(['code']);
    }
}
