<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Category;
use App\Models\City;
use App\Models\Company;
use App\Models\CompanyDocument;
use App\Models\Country;
use App\Models\User;
use Database\Seeders\CategorySeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Storage;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Визитка компании: фотогалерея из «Файлов и материалов»
 * и раздел «Услуги» в справочнике категорий.
 */
class CompanyCardExtrasTest extends TestCase
{
    use RefreshDatabase;

    #[Test]
    public function раздел_услуги_с_эйчаром_и_бухгалтерией(): void
    {
        $this->seed(CategorySeeder::class);

        $uslugi = Category::where('slug', 'uslugi')->first();

        $this->assertNotNull($uslugi);
        $this->assertSame('Услуги', $uslugi->name());

        $children = $uslugi->children()->pluck('slug')->all();

        $this->assertContains('hr-uslugi', $children);
        $this->assertContains('finansy-buhgalteriya', $children);
        $this->assertContains('uslugi-drugoe', $children);

        // «Другое» остаётся последним разделом — после «Услуг»
        $last = Category::whereNull('parent_id')->orderByDesc('sort')->first();
        $this->assertSame('drugoe', $last->slug);
    }

    /** Тип «Услуги»: онбординг отдаёт направления, компания сохраняет своё. */
    #[Test]
    public function онбординг_услуг_с_направлениями_и_своим_текстом(): void
    {
        $this->seed(CategorySeeder::class);

        $user = User::factory()->create(['email_verified_at' => now(), 'company_id' => null]);

        $this->actingAs($user)->get('/onboarding/company')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('serviceCategories', 3)
                ->where('serviceCategories.0.slug', 'hr-uslugi'));

        $hr = Category::where('slug', 'hr-uslugi')->firstOrFail();
        $other = Category::where('slug', 'uslugi-drugoe')->firstOrFail();

        $this->actingAs($user)->post('/onboarding/company', [
            'name' => 'Кадры Плюс',
            'type' => 'service',
            'country_id' => Country::firstOrCreate(['code' => 'uz'], ['phone_code' => '998', 'currency_code' => 'UZS', 'sort' => 1, 'is_active' => true])->id,
            'city_id' => City::firstOrCreate(['slug' => 'tashkent'], ['country_id' => Country::where('code', 'uz')->value('id'), 'is_active' => true])->id,
            'primary_role' => 'supplier',
            'categories' => [$hr->id, $other->id],
            'custom_category' => 'Аутсорсинг колл-центра',
        ])->assertSessionHasNoErrors();

        $company = $user->fresh()->company;

        $this->assertNotNull($company);
        $this->assertSame('Аутсорсинг колл-центра', $company->custom_category);
        $this->assertEqualsCanonicalizing([$hr->id, $other->id], $company->categories()->pluck('categories.id')->all());
    }

    #[Test]
    public function своё_направление_видно_на_визитке(): void
    {
        $company = Company::factory()->create(['custom_category' => 'Клининг офисов']);

        $this->get("/company/{$company->slug}")
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('company.custom_category', 'Клининг офисов'));
    }

    #[Test]
    public function публичное_фото_показывается_галереей(): void
    {
        Storage::fake('local');

        $company = Company::factory()->create();

        Storage::disk('local')->put('company-files/photo.jpg', 'jpg-bytes');

        $photo = CompanyDocument::create([
            'company_id' => $company->id,
            'type' => 'other',
            'title' => 'Наш склад',
            'file_path' => 'company-files/photo.jpg',
            'is_public' => true,
        ]);

        // Не картинка — остаётся файлом в списке
        Storage::disk('local')->put('company-files/price.pdf', 'pdf-bytes');
        CompanyDocument::create([
            'company_id' => $company->id,
            'type' => 'price_list',
            'title' => 'Прайс',
            'file_path' => 'company-files/price.pdf',
            'is_public' => true,
        ]);

        $this->get("/company/{$company->slug}")
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('files.0.is_image', true)
                ->where('files.1.is_image', false));

        // Фото отдаётся inline: галерея рисуется тегом img,
        // клик открывает картинку, а не скачивает файл
        $disposition = (string) $this->get("/files/{$photo->id}")
            ->assertOk()
            ->headers->get('Content-Disposition');

        $this->assertStringNotContainsString('attachment', $disposition);
    }

    #[Test]
    public function приватное_фото_в_галерею_не_попадает(): void
    {
        Storage::fake('local');

        $company = Company::factory()->create();

        Storage::disk('local')->put('company-files/secret.jpg', 'jpg');
        CompanyDocument::create([
            'company_id' => $company->id,
            'type' => 'other',
            'title' => 'Внутреннее',
            'file_path' => 'company-files/secret.jpg',
            'is_public' => false,
        ]);

        $this->get("/company/{$company->slug}")
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page->has('files', 0));
    }
}
