<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use App\Models\Category;
use App\Models\Company;
use App\Models\Listing;
use Database\Seeders\CategorySeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Теги объявления: выводятся из его же данных, ничего не хранится.
 *
 * Клик по тегу ведёт в поиск, поэтому набор обязан состоять из слов,
 * по которым это объявление находится: категория, значащие слова
 * заголовка, характеристики с числами, город. Служебные «куплю»
 * и «оптом» не годятся — тег о намерении не говорит о товаре.
 */
class ListingTagsTest extends TestCase
{
    use RefreshDatabase;

    #[Test]
    public function теги_собираются_из_категории_заголовка_и_характеристик(): void
    {
        $this->seed(CategorySeeder::class);

        $listing = Listing::factory()->create([
            'company_id' => Company::factory()->create()->id,
            'category_id' => Category::where('slug', 'poddony-tara')->value('id'),
            'status' => Listing::STATUS_ACTIVE,
            'published_at' => now()->subDay(),
            'title' => 'Куплю поддоны деревянные 1200х800, 2000 шт',
        ]);
        $listing->attributes()->create(['key' => 'size', 'value' => '1200×800 мм']);

        $this->get("/listing/{$listing->slug}")
            ->assertOk()
            ->assertInertia(function (AssertableInertia $page): void {
                $tags = $page->toArray()['props']['listing']['tags'];

                $this->assertContains('поддоны и тара', $tags, 'категория обязана быть тегом');
                $this->assertContains('поддоны', $tags, 'товар из заголовка обязан быть тегом');
                $this->assertContains('1200×800 мм', $tags, 'размер различает похожие позиции');
                $this->assertNotContains('куплю', $tags, 'намерение — не товар');
            });
    }
}
