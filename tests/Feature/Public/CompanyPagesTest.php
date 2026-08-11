<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\City;
use App\Models\Company;
use App\Models\CompanyContact;
use App\Models\Country;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Каталог компаний (§5.5 FR-CAT-00) и визитка (§5.2 FR-COMP-03).
 */
class CompanyPagesTest extends TestCase
{
    use RefreshDatabase;

    private function company(array $overrides = []): Company
    {
        $country = Country::firstOrCreate(
            ['code' => 'uz'],
            ['phone_code' => '998', 'currency_code' => 'UZS', 'is_active' => true],
        );
        $country->translations()->firstOrCreate(['locale' => 'ru'], ['name' => 'Узбекистан']);

        $city = City::firstOrCreate(['country_id' => $country->id, 'slug' => 'tashkent'], ['is_active' => true]);
        $city->translations()->firstOrCreate(['locale' => 'ru'], ['name' => 'Ташкент']);

        return Company::create(array_merge([
            'name' => 'ООО «Стройбаза»',
            'tin' => '304561278',
            'country_id' => $country->id,
            'city_id' => $city->id,
            'type' => 'distributor',
            'verification_level' => Company::VERIFICATION_COMPANY,
            'rating' => 4.8,
            'status' => Company::STATUS_ACTIVE,
        ], $overrides));
    }

    // ── Каталог ──────────────────────────────────────────────

    #[Test]
    public function каталог_компаний_открывается(): void
    {
        $this->company();

        $this->get('/companies')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->component('companies/Index')
                ->has('companies.data', 1)
                ->where('stats.total', 1),
            );
    }

    #[Test]
    public function заблокированные_компании_в_каталог_не_попадают(): void
    {
        $this->company();
        $this->company(['name' => 'Заблокированная', 'tin' => '111111111', 'status' => Company::STATUS_BLOCKED]);

        $this->get('/companies')
            ->assertInertia(fn (AssertableInertia $page) => $page->has('companies.data', 1));
    }

    #[Test]
    public function поиск_работает_по_названию_и_по_инн(): void
    {
        $this->company();
        $this->company(['name' => 'Другая компания', 'tin' => '999999999']);

        $this->get('/companies?q=Стройбаза')
            ->assertInertia(fn (AssertableInertia $page) => $page->has('companies.data', 1));

        $this->get('/companies?q=999999999')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('companies.data', 1)
                ->where('companies.data.0.name', 'Другая компания'),
            );
    }

    #[Test]
    public function фильтр_только_проверенные_отсекает_непроверенные(): void
    {
        $this->company();
        $this->company([
            'name' => 'Новичок',
            'tin' => '222222222',
            'verification_level' => Company::VERIFICATION_NONE,
        ]);

        $this->get('/companies')
            ->assertInertia(fn (AssertableInertia $page) => $page->has('companies.data', 2));

        $this->get('/companies?verified=1')
            ->assertInertia(fn (AssertableInertia $page) => $page->has('companies.data', 1));
    }

    #[Test]
    public function фильтр_по_дате_регистрации_делит_компании_на_возрастные_группы(): void
    {
        $fresh = $this->company();
        $middle = $this->company(['name' => 'Середняк', 'tin' => '333333333']);
        $middle->forceFill(['created_at' => now()->subYears(3)])->save();
        $old = $this->company(['name' => 'Ветеран', 'tin' => '444444444']);
        $old->forceFill(['created_at' => now()->subYears(6)])->save();

        $this->get('/companies?age=lt1')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('companies.data', 1)
                ->where('companies.data.0.name', $fresh->name));

        $this->get('/companies?age=1to5')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('companies.data', 1)
                ->where('companies.data.0.name', 'Середняк'));

        $this->get('/companies?age=gt5')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('companies.data', 1)
                ->where('companies.data.0.name', 'Ветеран'));

        // Мусор из адресной строки не фильтрует и не ломает страницу
        $this->get('/companies?age=чепуха')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page->has('companies.data', 3));
    }

    #[Test]
    public function пустая_выдача_не_ломает_страницу(): void
    {
        $this->company();

        $this->get('/companies?q=такогонетточно')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page->has('companies.data', 0));
    }

    // ── Визитка ──────────────────────────────────────────────

    #[Test]
    public function визитка_показывает_реквизиты(): void
    {
        $company = $this->company();

        $this->get("/company/{$company->slug}")
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->component('companies/Show')
                ->where('company.name', 'ООО «Стройбаза»')
                ->where('company.tin', '304561278')
                ->where('company.city', 'Ташкент')
                ->where('company.country', 'Узбекистан')
                ->where('initials', 'СТ'),
            );
    }

    #[Test]
    public function несуществующая_компания_даёт_404(): void
    {
        $this->get('/company/net-takoy')->assertNotFound();
    }

    /**
     * NEG: контакты не должны утекать в HTML до оплаты.
     * Это главный риск модели — если полный номер попадёт в ответ сервера,
     * его достанут из исходного кода страницы, не заплатив.
     */
    #[Test]
    public function гостю_контакты_приходят_только_замаскированными(): void
    {
        $company = $this->company();
        CompanyContact::create([
            'company_id' => $company->id,
            'type' => CompanyContact::TYPE_PHONE,
            'value' => '+998901234567',
            'label' => 'Отдел продаж',
            'is_public' => true,
        ]);
        CompanyContact::create([
            'company_id' => $company->id,
            'type' => CompanyContact::TYPE_EMAIL,
            'value' => 'sales@stroybaza.uz',
            'is_public' => true,
        ]);

        $response = $this->get("/company/{$company->slug}");

        $response->assertInertia(fn (AssertableInertia $page) => $page
            ->where('unlocked', false)
            ->has('contacts', 2)
            ->where('contacts.0.href', null),
        );

        // Полного номера и адреса нет нигде в ответе, включая исходный код
        $response->assertDontSee('+998901234567');
        $response->assertDontSee('901234567');
        $response->assertDontSee('sales@stroybaza.uz');
    }

    #[Test]
    public function маска_оставляет_код_оператора_и_домен(): void
    {
        $company = $this->company();
        CompanyContact::create([
            'company_id' => $company->id,
            'type' => CompanyContact::TYPE_PHONE,
            'value' => '+998 90 123-45-67',
            'is_public' => true,
        ]);

        $this->get("/company/{$company->slug}")
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('contacts.0.value', '+998 90 ••• •• ••'),
            );
    }

    #[Test]
    public function сотрудник_компании_видит_свои_контакты_целиком(): void
    {
        $company = $this->company();
        CompanyContact::create([
            'company_id' => $company->id,
            'type' => CompanyContact::TYPE_PHONE,
            'value' => '+998901234567',
            'is_public' => true,
        ]);

        $user = User::factory()->create(['company_id' => $company->id]);

        $this->actingAs($user)
            ->get("/company/{$company->slug}")
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('unlocked', true)
                ->where('contacts.0.value', '+998901234567')
                ->where('contacts.0.href', 'tel:+998901234567'),
            );
    }

    #[Test]
    public function непубличные_контакты_не_отдаются_наружу(): void
    {
        $company = $this->company();
        CompanyContact::create([
            'company_id' => $company->id,
            'type' => CompanyContact::TYPE_PHONE,
            'value' => '+998901234567',
            'is_public' => true,
        ]);
        CompanyContact::create([
            'company_id' => $company->id,
            'type' => CompanyContact::TYPE_PHONE,
            'value' => '+998900000001',
            'label' => 'Прямой номер директора',
            'is_public' => false,
        ]);

        $this->get("/company/{$company->slug}")
            ->assertInertia(fn (AssertableInertia $page) => $page->has('contacts', 1));
    }
}
