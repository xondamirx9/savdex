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
use Tests\TestCase;

/**
 * Регистрация: юридическое лицо, физическое лицо или фрилансер.
 *
 * Выбор делается на первом шаге и определяет второй: физлицу
 * и фрилансеру не нужны название компании и тип бизнеса.
 */
class AccountTypeTest extends TestCase
{
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
        $this->post('/register', array_filter([
            'name' => 'Алишер Каримов',
            'email' => 'alisher@mail.uz',
            'phone' => '+998 90 123-45-67',
            'password' => 'Parol-12345',
            'password_confirmation' => 'Parol-12345',
            'terms' => true,
            'account_type' => $type,
        ], fn ($v) => $v !== null))->assertRedirect('/onboarding/company');
    }

    #[Test]
    public function выбор_запоминается_а_без_выбора_это_юрлицо(): void
    {
        $this->register('freelancer');
        $this->assertSame('freelancer', User::where('email', 'alisher@mail.uz')->value('account_type'));

        auth()->logout();
        User::query()->forceDelete();

        $this->register(null);
        $this->assertSame('legal', User::where('email', 'alisher@mail.uz')->value('account_type'));
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
