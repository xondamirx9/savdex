<?php

declare(strict_types=1);

namespace Tests\Feature\Auth;

use App\Models\Category;
use App\Models\City;
use App\Models\Company;
use App\Models\Country;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Второй шаг регистрации — данные компании.
 *
 * По прототипу регистрация двухшаговая: аккаунт, затем компания.
 * Шаг пропускаемый: аккаунт уже создан, и упереться в форму здесь
 * значит потерять человека совсем.
 */
class OnboardingTest extends TestCase
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

    #[Test]
    public function регистрация_ведёт_на_шаг_компании(): void
    {
        $this->post('/register', [
            'name' => 'Рустам Каримов',
            'email' => 'rustam@company.uz',
            'phone' => '+998 90 123-45-67',
            'password' => 'Parol-12345',
            'password_confirmation' => 'Parol-12345',
            'terms' => true,
        ])->assertRedirect('/onboarding/company');
    }

    #[Test]
    public function шаг_открывается_и_отдаёт_справочники(): void
    {
        $this->geo();
        $category = Category::create(['slug' => 'stroymaterialy', 'is_active' => true, 'sort' => 1]);
        $category->translations()->create(['locale' => 'ru', 'name' => 'Стройматериалы']);

        $this->actingAs(User::factory()->create(['company_id' => null]))
            ->get('/onboarding/company')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->component('auth/CompanyStep')
                ->has('countries', 1)
                ->has('cities', 1)
                ->has('categories', 1)
                ->has('types'),
            );
    }

    /**
     * ИНН (СТИР) в Узбекистане — ровно 9 цифр, и учебные значения
     * («123456789», повторы) не проходят: «ооо ромашка, ИНН 123456789»
     * в боевом каталоге подрывает доверие сильнее пустого поля.
     */
    #[Test]
    public function недействительный_инн_отклоняется(): void
    {
        [$country, $city] = $this->geo();
        $user = User::factory()->create(['company_id' => null]);

        $payload = fn (string $tin): array => [
            'name' => 'ООО «Стройбаза»',
            'type' => 'manufacturer',
            'country_id' => $country->id,
            'city_id' => $city->id,
            'primary_role' => 'supplier',
            'tin' => $tin,
        ];

        foreach (['123456789', '2345678', '111111111', '30456127a'] as $tin) {
            $this->actingAs($user)
                ->post('/onboarding/company', $payload($tin))
                ->assertSessionHasErrors('tin');
        }

        $this->assertSame(0, Company::count());

        $this->actingAs($user)
            ->post('/onboarding/company', $payload('304561278'))
            ->assertSessionHasNoErrors();

        $this->assertSame('304561278', Company::firstOrFail()->tin);
    }

    #[Test]
    public function повторный_инн_отклоняется(): void
    {
        [$country, $city] = $this->geo();
        Company::factory()->create(['tin' => '304561278']);

        $this->actingAs(User::factory()->create(['company_id' => null]))
            ->post('/onboarding/company', [
                'name' => 'ООО «Дубль»',
                'type' => 'manufacturer',
                'country_id' => $country->id,
                'city_id' => $city->id,
                'primary_role' => 'supplier',
                'tin' => '304561278',
            ])
            ->assertSessionHasErrors('tin');
    }

    #[Test]
    public function компания_создаётся_и_привязывается_к_пользователю(): void
    {
        [$country, $city] = $this->geo();
        $user = User::factory()->create(['company_id' => null]);

        $this->actingAs($user)
            ->post('/onboarding/company', [
                'name' => 'ООО «Стройбаза»',
                'type' => 'distributor',
                'country_id' => $country->id,
                'city_id' => $city->id,
                'tin' => '304561278',
                'primary_role' => 'supplier',
            ])
            ->assertRedirect('/verify-email');

        $company = Company::first();

        $this->assertNotNull($company);
        $this->assertSame('ООО «Стройбаза»', $company->name);
        $this->assertSame($company->id, $user->fresh()->company_id);
        $this->assertSame('owner', $user->fresh()->company_role);

        // slug строится хуком модели — без него визитка недоступна
        $this->assertNotEmpty($company->slug);
    }

    #[Test]
    public function категории_сохраняются(): void
    {
        [$country, $city] = $this->geo();

        $categories = collect(['stroymaterialy', 'metally'])->map(function (string $slug): Category {
            $category = Category::create(['slug' => $slug, 'is_active' => true]);
            $category->translations()->create(['locale' => 'ru', 'name' => $slug]);

            return $category;
        });

        $user = User::factory()->create(['company_id' => null]);

        $this->actingAs($user)->post('/onboarding/company', [
            'name' => 'ООО «Стройбаза»',
            'type' => 'distributor',
            'country_id' => $country->id,
            'city_id' => $city->id,
            'primary_role' => 'both',
            'categories' => $categories->pluck('id')->all(),
        ]);

        $this->assertSame(2, Company::first()->categories()->count());
    }

    /**
     * Больше пяти категорий — профиль перестаёт что-либо говорить
     * о компании, поэтому предел жёсткий.
     */
    #[Test]
    public function больше_пяти_категорий_отклоняется(): void
    {
        [$country, $city] = $this->geo();

        $ids = collect(range(1, 6))->map(function (int $i): int {
            $category = Category::create(['slug' => "cat-{$i}", 'is_active' => true]);
            $category->translations()->create(['locale' => 'ru', 'name' => "Категория {$i}"]);

            return $category->id;
        })->all();

        $this->actingAs(User::factory()->create(['company_id' => null]))
            ->post('/onboarding/company', [
                'name' => 'ООО «Стройбаза»',
                'type' => 'distributor',
                'country_id' => $country->id,
                'city_id' => $city->id,
                'primary_role' => 'both',
                'categories' => $ids,
            ])
            ->assertSessionHasErrors('categories');

        $this->assertSame(0, Company::count());
    }

    #[Test]
    public function шаг_можно_пропустить(): void
    {
        $user = User::factory()->create(['company_id' => null]);

        $this->actingAs($user)
            ->post('/onboarding/skip')
            ->assertRedirect('/verify-email')
            ->assertSessionHas('warning');

        $this->assertNull($user->fresh()->company_id);
    }

    /** Повторно проходить шаг незачем — компания уже есть. */
    #[Test]
    public function с_компанией_шаг_пропускается_автоматически(): void
    {
        $company = Company::factory()->create();
        $user = User::factory()->create(['company_id' => $company->id]);

        $this->actingAs($user)->get('/onboarding/company')->assertRedirect('/cabinet');

        $this->actingAs($user)->post('/onboarding/company', [
            'name' => 'Другая компания',
            'type' => 'trader',
        ])->assertRedirect('/cabinet');

        $this->assertSame(1, Company::count());
    }

    #[Test]
    public function гость_на_шаг_не_попадает(): void
    {
        $this->get('/onboarding/company')->assertRedirect('/login');
    }
}
