<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\Category;
use App\Models\Company;
use App\Models\Listing;
use App\Models\User;
use App\Support\ProductSpecs;
use Database\Seeders\PlanSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * «Информация о товаре»: вес, размеры, цвет, материал на шаге
 * «Товар и цена» мастера объявления.
 *
 * Поля зависят от категории, заполнять их необязательно, на карточке
 * товара они выводятся на языке посетителя.
 */
class ProductSpecsTest extends TestCase
{
    use RefreshDatabase;

    private User $user;

    private Company $company;

    protected function setUp(): void
    {
        parent::setUp();

        $this->seed(PlanSeeder::class);

        $this->company = Company::factory()->create();
        $this->user = User::factory()->for($this->company)->create();
    }

    private function category(string $parentSlug, string $childSlug): Category
    {
        $parent = Category::factory()->create(['slug' => $parentSlug, 'parent_id' => null]);

        return Category::factory()->create(['slug' => $childSlug, 'parent_id' => $parent->id]);
    }

    private function draft(Category $category): Listing
    {
        return Listing::factory()->draft()->create([
            'company_id' => $this->company->id,
            'user_id' => $this->user->id,
            'category_id' => $category->id,
        ]);
    }

    /** @return list<string> */
    private function keys(?string $parent, ?string $child): array
    {
        return array_column(ProductSpecs::form($parent, $child), 'key');
    }

    #[Test]
    public function поля_подобраны_под_товар(): void
    {
        // Металл — толщина, диаметр, марка, но не срок годности
        $metal = $this->keys('metally', 'chernye-metally');
        $this->assertContains('spec_thickness', $metal);
        $this->assertContains('spec_grade', $metal);
        $this->assertNotContains('spec_shelf_life', $metal);

        // Металлопрокат лежит в стройматериалах, но описывается как металл
        $this->assertSame($metal, $this->keys('stroymaterialy', 'metalloprokat'));

        // Продукты — срок годности и хранение, без размеров
        $food = $this->keys('produkty', 'sukhofrukty');
        $this->assertContains('spec_shelf_life', $food);
        $this->assertNotContains('spec_dimensions', $food);

        // Материалы — из своего раздела: у ткани нет бетона
        $textile = collect(ProductSpecs::form('tekstil', 'pryazha-tkani'))->firstWhere('key', 'spec_composition');
        $this->assertContains('cotton', array_column($textile['options'], 'value'));
        $this->assertNotContains('concrete', array_column($textile['options'], 'value'));

        // У услуг блока нет, новый раздел получает общий набор
        $this->assertSame([], $this->keys('uslugi', 'hr-uslugi'));
        $this->assertContains('spec_weight', $this->keys('novyy-razdel', 'chto-to'));
    }

    #[Test]
    public function мастер_отдаёт_поля_вместе_с_категориями(): void
    {
        $category = $this->category('metally', 'chernye-metally');
        $listing = $this->draft($category);

        $this->actingAs($this->user)->get('/cabinet/listings/'.$listing->id.'/edit')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('categories.0.children.0.specs', fn ($specs) => collect($specs)->pluck('key')->contains('spec_thickness')));
    }

    #[Test]
    public function детали_сохраняются_проверенными_а_пустые_удаляются(): void
    {
        $listing = $this->draft($this->category('metally', 'chernye-metally'));

        $this->actingAs($this->user)->postJson('/cabinet/listings/'.$listing->id.'/autosave', [
            'attributes' => [
                'spec_weight' => '25,5 kg',
                'spec_material' => 'steel',
                'spec_grade' => 'Ст3 <b>ГОСТ</b>',
                // Мусор отбрасывается: чужая единица, чужой ключ
                'spec_thickness' => '5 parsecs',
                'spec_hack' => 'x',
            ],
        ])->assertOk();

        $values = $listing->attributes()->pluck('value', 'key');

        $this->assertSame('25.5 kg', $values['spec_weight']);
        $this->assertSame('steel', $values['spec_material']);
        $this->assertSame('Ст3 ГОСТ', $values['spec_grade']);
        $this->assertArrayNotHasKey('spec_thickness', $values->all());
        $this->assertArrayNotHasKey('spec_hack', $values->all());

        // Очищенное поле удаляется, а не хранится пустым
        $this->actingAs($this->user)->postJson('/cabinet/listings/'.$listing->id.'/autosave', [
            'attributes' => ['spec_weight' => ''],
        ])->assertOk();

        $this->assertFalse($listing->attributes()->where('key', 'spec_weight')->exists());
    }

    #[Test]
    public function смена_категории_убирает_чужие_детали(): void
    {
        $listing = $this->draft($this->category('metally', 'chernye-metally'));
        $food = $this->category('produkty', 'sukhofrukty');

        $this->actingAs($this->user)->postJson('/cabinet/listings/'.$listing->id.'/autosave', [
            'attributes' => ['spec_thickness' => '5 mm', 'spec_origin' => 'Узбекистан'],
        ])->assertOk();

        $this->actingAs($this->user)->postJson('/cabinet/listings/'.$listing->id.'/autosave', [
            'category_id' => $food->id,
        ])->assertOk();

        $keys = $listing->attributes()->pluck('key')->all();

        $this->assertNotContains('spec_thickness', $keys);
        // Страна производства есть и у продуктов — остаётся
        $this->assertContains('spec_origin', $keys);
    }

    #[Test]
    public function без_деталей_объявление_публикуется(): void
    {
        $listing = $this->draft($this->category('metally', 'chernye-metally'));

        $this->actingAs($this->user)->post('/cabinet/listings/'.$listing->id.'/publish', [
            'category_id' => $listing->category_id,
            'title' => 'Арматура А500С диаметр 12 мм',
            'description' => 'Арматура рифлёная А500С, диаметр 12 мм, длина прутка 11,7 м. Отгрузка со склада в Ташкенте.',
            'price' => 9500000,
            'currency' => 'UZS',
            'price_negotiable' => false,
        ])->assertSessionHasNoErrors();

        $this->assertSame(Listing::STATUS_ACTIVE, $listing->fresh()->status);
    }

    #[Test]
    public function карточка_показывает_детали_на_языке_посетителя(): void
    {
        $listing = Listing::factory()->create([
            'company_id' => $this->company->id,
            'category_id' => $this->category('mebel', 'ofisnaya-mebel')->id,
        ]);
        $listing->attributes()->createMany([
            ['key' => 'spec_dimensions', 'value' => '120x60x75 cm'],
            ['key' => 'spec_color', 'value' => 'black'],
            ['key' => 'spec_weight', 'value' => '25 kg'],
        ]);

        $this->get('/listing/'.$listing->slug)->assertInertia(fn (AssertableInertia $page) => $page
            ->where('listing.attributes', fn ($rows) => collect($rows)->contains(
                fn ($r) => $r['key'] === 'Размеры (Д × Ш × В)' && $r['value'] === '120 × 60 × 75 см',
            ) && collect($rows)->contains(fn ($r) => $r['key'] === 'Цвет' && $r['value'] === 'Чёрный')));

        $this->get('/en/listing/'.$listing->slug)->assertInertia(fn (AssertableInertia $page) => $page
            ->where('listing.attributes', fn ($rows) => collect($rows)->contains(
                fn ($r) => $r['key'] === 'Weight' && $r['value'] === '25 kg',
            ) && collect($rows)->contains(fn ($r) => $r['key'] === 'Colour' && $r['value'] === 'Black')));
    }

    /** Словарь деталей не должен разъезжаться между языками. */
    #[Test]
    public function словари_деталей_совпадают_по_ключам(): void
    {
        $reference = $this->flat((array) trans('specs', locale: 'ru'));

        foreach (['en', 'uz', 'tr', 'zh'] as $locale) {
            $this->assertSame($reference, $this->flat((array) trans('specs', locale: $locale)), "Словарь specs.{$locale} разошёлся с русским");
        }
    }

    /**
     * @param  array<string, mixed>  $dictionary
     * @return list<string>
     */
    private function flat(array $dictionary, string $prefix = ''): array
    {
        $keys = [];

        foreach ($dictionary as $key => $value) {
            $keys = is_array($value)
                ? [...$keys, ...$this->flat($value, $prefix.$key.'.')]
                : [...$keys, $prefix.$key];
        }

        sort($keys);

        return $keys;
    }
}
