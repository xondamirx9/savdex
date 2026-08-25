<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Category;
use App\Models\Company;
use App\Models\Listing;
use App\Models\User;
use Database\Seeders\CategorySeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Категория «Другое» со свободным полем «Категория товара».
 *
 * Товару без готовой рубрики нужно место: в каждом разделе есть
 * подкатегория «Другое», и у неё текстовое поле, где продавец сам
 * называет категорию. Название видно на карточке объявления —
 * с человеческой подписью, а не служебным ключом.
 */
class CustomCategoryTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();

        $this->seed(CategorySeeder::class);
    }

    #[Test]
    public function в_каждом_разделе_есть_другое_со_свободным_полем(): void
    {
        $parents = Category::whereNull('parent_id')->where('is_active', true)->get();

        $this->assertNotEmpty($parents);

        foreach ($parents as $parent) {
            $other = $parent->children()
                ->whereIn('slug', ["{$parent->slug}-drugoe", 'raznye-tovary'])
                ->first();

            $this->assertNotNull($other, "В разделе {$parent->slug} нет подкатегории «Другое»");
            $this->assertNotNull(
                $other->fields()->where('key', 'custom_category')->first(),
                "У {$other->slug} нет поля «Категория товара»",
            );
        }
    }

    #[Test]
    public function своя_категория_видна_на_карточке_с_подписью(): void
    {
        $company = Company::factory()->create();
        $user = User::factory()->for($company)->create(['email_verified_at' => now()]);

        $listing = Listing::create([
            'company_id' => $company->id,
            'user_id' => $user->id,
            'category_id' => Category::where('slug', 'raznye-tovary')->value('id'),
            'status' => Listing::STATUS_ACTIVE,
            'type' => Listing::TYPE_SUPPLY,
            'title' => 'Крепёж и метизы оптом, отгрузка со склада',
            'currency' => 'UZS',
            'published_at' => now(),
        ]);
        $listing->forceFill(['slug' => Listing::makeSlug($listing->title, $listing->id)])->save();
        $listing->attributes()->create(['key' => 'custom_category', 'value' => 'Крепёж и метизы']);

        $this->get("/listing/{$listing->slug}")
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('listing.attributes.0.key', 'Категория товара')
                ->where('listing.attributes.0.value', 'Крепёж и метизы'));
    }

    /** Подписи работают и для обычных категорий: «Марка», а не mark. */
    #[Test]
    public function ключи_характеристик_показываются_подписями(): void
    {
        $company = Company::factory()->create();
        $user = User::factory()->for($company)->create(['email_verified_at' => now()]);

        $listing = Listing::create([
            'company_id' => $company->id,
            'user_id' => $user->id,
            'category_id' => Category::where('slug', 'cement-beton')->value('id'),
            'status' => Listing::STATUS_ACTIVE,
            'type' => Listing::TYPE_SUPPLY,
            'title' => 'Цемент М400 навалом, отгрузка с завода',
            'currency' => 'UZS',
            'published_at' => now(),
        ]);
        $listing->forceFill(['slug' => Listing::makeSlug($listing->title, $listing->id)])->save();
        $listing->attributes()->create(['key' => 'mark', 'value' => 'М400']);

        $this->get("/listing/{$listing->slug}")
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('listing.attributes.0.key', 'Марка')
                ->where('listing.attributes.0.value', 'М400'));
    }
}
