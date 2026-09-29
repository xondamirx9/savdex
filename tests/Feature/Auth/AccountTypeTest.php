<?php

declare(strict_types=1);

namespace Tests\Feature\Auth;

use App\Models\City;
use App\Models\Company;
use App\Models\Country;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\Support\LegalRegistration;
use Tests\TestCase;

/**
 * Регистрация: юридическое лицо, физическое лицо или фрилансер.
 *
 * Выбор делается на первом шаге и определяет второй: физлицу
 * и фрилансеру не нужны название компании и тип бизнеса.
 */
class AccountTypeTest extends TestCase
{
    use LegalRegistration;
    use RefreshDatabase;

    private function geo(): array
    {
        $country = Country::create([
            'code' => 'uz',
            'phone_code' => '998',
            'currency_code' => 'UZS',
            'is_active' => true,
            'sort' => 1,
        ]);
        $country->translations()->create(['locale' => 'ru', 'name' => 'Узбекистан']);

        $city = City::create(['country_id' => $country->id, 'slug' => 'tashkent', 'is_active' => true]);
        $city->translations()->create(['locale' => 'ru', 'name' => 'Ташкент']);

        return [$country, $city];
    }

    private function register(?string $type): void
    {
        $fields = match ($type) {
            'freelancer' => ['pinfl' => '31234567890123', 'service_section' => 'it'],
            'individual' => [],
            default => $this->legalFields(),
        };

        $this->post('/register', array_filter([
            'name' => 'Алишер Каримов',
            'email' => 'alisher@mail.uz',
            'phone' => '+998 90 123-45-67',
            'password' => 'Parol-12345',
            'password_confirmation' => 'Parol-12345',
            'terms' => true,
            'account_type' => $type,
            ...$fields,
        ], fn ($v) => $v !== null))->assertSessionHasNoErrors()->assertRedirect(
            // Второй шаг «Данные компании» — только у юрлица
            in_array($type, ['freelancer', 'individual'], true) ? '/verify-email' : '/onboarding/company'
        );
    }

    #[Test]
    public function выбор_запоминается_а_без_выбора_это_юрлицо(): void
    {
        $this->register('freelancer');
        $this->assertSame('freelancer', User::where('email', 'alisher@mail.uz')->value('account_type'));

        auth()->logout();
        User::query()->forceDelete();
        Company::query()->forceDelete();

        $this->register(null);
        $this->assertSame('legal', User::where('email', 'alisher@mail.uz')->value('account_type'));
    }

    #[Test]
    public function юрлицо_заводит_компанию_с_первого_шага(): void
    {
        $this->register('legal');

        $company = User::where('email', 'alisher@mail.uz')->firstOrFail()->company;

        $this->assertNotNull($company);
        $this->assertSame('ООО «Стройбаза»', $company->name);
        $this->assertSame(Company::LEGAL_ENTITY, $company->legal_form);
        $this->assertCount(1, $company->categories);
    }

    #[Test]
    public function второй_шаг_юрлица_дополняет_компанию_без_повторных_вопросов(): void
    {
        [$country, $city] = $this->geo();
        $this->register('legal');
        $user = User::where('email', 'alisher@mail.uz')->firstOrFail();

        $this->actingAs($user)->get('/onboarding/company')
            ->assertInertia(fn (AssertableInertia $page) => $page->where('completing', true));

        $this->actingAs($user)->post('/onboarding/company', [
            'type' => 'distributor',
            'country_id' => $country->id,
            'city_id' => $city->id,
            'primary_role' => 'supplier',
        ])->assertSessionHasNoErrors();

        $company = $user->fresh()->company;

        $this->assertSame('ООО «Стройбаза»', $company->name);
        $this->assertSame($city->id, $company->city_id);
        $this->assertSame('supplier', $company->primary_role);
        // Категории с первого шага не потерялись
        $this->assertCount(1, $company->categories);
        // Шаг пройден — второй раз не показывается
        $this->actingAs($user)->get('/onboarding/company')->assertRedirect('/cabinet');
    }

    #[Test]
    public function юрлицу_нужны_название_и_категория_а_инн_по_желанию(): void
    {
        $this->post('/register', [
            'name' => 'Алишер Каримов',
            'email' => 'alisher@mail.uz',
            'phone' => '+998 90 123-45-67',
            'password' => 'Parol-12345',
            'password_confirmation' => 'Parol-12345',
            'terms' => true,
            'account_type' => 'legal',
        ])->assertSessionHasErrors(['company_name', 'categories'])
            ->assertSessionDoesntHaveErrors(['tin', 'pinfl', 'service_section']);
    }

    #[Test]
    public function физлицо_регистрируется_без_второго_шага_и_пинфл_по_желанию(): void
    {
        $this->register('individual');

        $user = User::where('email', 'alisher@mail.uz')->firstOrFail();

        $this->assertSame(Company::LEGAL_INDIVIDUAL, $user->company->legal_form);
        // Профиль человека называется по Ф.И.О.
        $this->assertSame('Алишер Каримов', $user->company->name);
        $this->assertNull($user->company->tin);
        $this->assertNull($user->company->city_id);

        // Второй шаг физлицу не показывается
        $this->actingAs($user)->get('/onboarding/company')->assertRedirect('/cabinet');
    }

    #[Test]
    public function фрилансеру_нужны_пинфл_и_направление(): void
    {
        $this->post('/register', [
            'name' => 'Алишер Каримов',
            'email' => 'alisher@mail.uz',
            'phone' => '+998 90 123-45-67',
            'password' => 'Parol-12345',
            'password_confirmation' => 'Parol-12345',
            'terms' => true,
            'account_type' => 'freelancer',
            'pinfl' => '123456789',
        ])->assertSessionHasErrors(['pinfl', 'service_section'])
            ->assertSessionDoesntHaveErrors(['company_name', 'categories']);
    }

    #[Test]
    public function фрилансер_сразу_исполнитель_своего_направления(): void
    {
        $this->register('freelancer');

        $company = User::where('email', 'alisher@mail.uz')->firstOrFail()->company;

        $this->assertSame(Company::LEGAL_FREELANCER, $company->legal_form);
        $this->assertSame('31234567890123', $company->tin);
        $this->assertTrue((bool) $company->is_it_provider);
        $this->assertContains('web', $company->it_specializations);
    }

    #[Test]
    public function неизвестный_тип_отклоняется(): void
    {
        $this->post('/register', [
            'name' => 'Алишер Каримов',
            'email' => 'alisher@mail.uz',
            'phone' => '+998 90 123-45-67',
            'password' => 'Parol-12345',
            'password_confirmation' => 'Parol-12345',
            'terms' => true,
            'account_type' => 'government',
        ])->assertSessionHasErrors('account_type');
    }

    #[Test]
    public function физлицо_создаёт_профиль_без_типа_бизнеса_и_с_пинфл(): void
    {
        [$country, $city] = $this->geo();
        $user = User::factory()->create(['company_id' => null, 'account_type' => 'individual', 'name' => 'Алишер Каримов']);

        $this->actingAs($user)->get('/onboarding/company')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('accountType', 'individual')
                ->where('personName', 'Алишер Каримов'));

        $this->actingAs($user)->post('/onboarding/company', [
            'name' => 'Алишер Каримов',
            'country_id' => $country->id,
            'city_id' => $city->id,
            // ПИНФЛ — 14 цифр: физлицу его принимаем
            'tin' => '31234567890123',
            'primary_role' => 'buyer',
        ])->assertSessionHasNoErrors();

        $company = $user->fresh()->company;

        $this->assertSame(Company::LEGAL_INDIVIDUAL, $company->legal_form);
        $this->assertNull($company->type);
        // Карточка подписана формой, а не пустотой
        $this->assertSame('Физическое лицо', $company->typeLabel());
    }

    #[Test]
    public function юрлицу_тип_обязателен_а_пинфл_не_подходит(): void
    {
        [$country, $city] = $this->geo();
        $user = User::factory()->create(['company_id' => null, 'account_type' => 'legal']);

        $this->actingAs($user)->post('/onboarding/company', [
            'name' => 'ООО «Стройбаза»',
            'country_id' => $country->id,
            'city_id' => $city->id,
            'tin' => '31234567890123',
            'primary_role' => 'supplier',
        ])->assertSessionHasErrors(['type', 'tin']);
    }

    #[Test]
    public function фрилансер_на_витрине_подписан_фрилансером(): void
    {
        $company = Company::factory()->create(['type' => null]);
        $company->forceFill(['legal_form' => Company::LEGAL_FREELANCER])->save();

        $this->get('/company/'.$company->slug)
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('company.legal_form', 'freelancer')
                ->where('company.type_label', 'Фрилансер'));
    }
}
