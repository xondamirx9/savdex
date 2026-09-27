<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Exceptions\RecordIsReferenced;
use App\Models\Category;
use App\Models\Company;
use App\Models\Listing;
use Database\Seeders\CategorySeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Правила категорий, которые остались в модели Laravel.
 *
 * Раздел с этапа 2 переноса работает на Python
 * (python/savdex/catalogs/admin.py, проверки —
 * python/tests/test_categories_admin.py). Здесь — то, что обязано
 * держаться, кто бы ни правил: запрет удаления и сидер.
 */
class CategoriesTest extends TestCase
{
    use RefreshDatabase;

    /**
     * @param  callable(Category): void  $hold
     * @param  array<string, int>  $expected
     */
    private function assertHeld(callable $hold, array $expected): void
    {
        $category = Category::factory()->named('Цемент')->create();
        $hold($category);

        try {
            $category->delete();
            $this->fail('категория удалилась, хотя на неё ссылаются');
        } catch (RecordIsReferenced $e) {
            $this->assertSame($expected, $e->references);
        }

        $this->assertModelExists($category);
    }

    /** Подкатегории раздела молча становились разделами — внешний ключ nullOnDelete. */
    #[Test]
    public function раздел_с_подкатегориями_не_удаляется(): void
    {
        $this->assertHeld(
            fn (Category $c) => Category::factory()->child($c)->create(),
            ['подкатегории' => 1],
        );
    }

    /** Удалённое в корзину объявление тоже держит: восстановленное вернулось бы без категории. */
    #[Test]
    public function объявления_держат_категорию_даже_из_корзины(): void
    {
        $this->assertHeld(
            fn (Category $c) => Listing::factory()->create(['category_id' => $c->id])->delete(),
            ['объявления' => 1],
        );
    }

    /** Привязки компаний к категории стирались каскадом. */
    #[Test]
    public function категория_с_компаниями_не_удаляется(): void
    {
        $this->assertHeld(
            fn (Category $c) => Company::factory()->create()->categories()->attach($c),
            ['компании' => 1],
        );
    }

    #[Test]
    public function пустая_категория_удаляется(): void
    {
        $category = Category::factory()->create();

        $category->delete();

        $this->assertModelMissing($category);
    }

    /**
     * Деплой не откатывает правки категорий.
     *
     * CategorySeeder гоняется на каждом деплое и раньше перезаписывал
     * существующие категории: выключенная в админке включалась обратно,
     * переименованная возвращала старое имя, перенесённая — старый раздел.
     */
    #[Test]
    public function сидер_не_откатывает_правки_категорий(): void
    {
        $this->seed(CategorySeeder::class);

        $cement = Category::where('slug', 'cement-beton')->firstOrFail();
        $other = Category::where('slug', 'metally')->firstOrFail();
        $cement->update(['is_active' => false, 'sort' => 42, 'parent_id' => $other->id]);
        $cement->translations()->where('locale', 'ru')->update(['name' => 'Бетон']);
        $count = Category::count();

        $this->seed(CategorySeeder::class);

        $cement->refresh()->load('translations');
        $this->assertFalse($cement->is_active);
        $this->assertSame(42, $cement->sort);
        $this->assertSame($other->id, $cement->parent_id);
        $this->assertSame('Бетон', $cement->name('ru'));
        $this->assertSame($count, Category::count(), 'дублей нет');
    }

    /** На свежей базе сидер заводит дерево со всеми названиями и полями. */
    #[Test]
    public function сидер_заводит_категории_на_свежей_базе(): void
    {
        $this->seed(CategorySeeder::class);

        $cement = Category::where('slug', 'cement-beton')->with('translations')->firstOrFail();

        $this->assertTrue($cement->is_active);
        $this->assertSame('Цемент и бетон', $cement->name('ru'));
        $this->assertCount(5, $cement->translations);
        $this->assertSame('stroymaterialy', $cement->parent?->slug);
    }
}
