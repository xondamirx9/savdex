<?php

declare(strict_types=1);

namespace Database\Factories;

use App\Models\Category;
use Illuminate\Database\Eloquent\Factories\Factory;
use Illuminate\Support\Str;

/**
 * @extends Factory<Category>
 *
 * Модель объявляла HasFactory<CategoryFactory>, а самой фабрики не было:
 * Category::factory() падал с «class not found».
 */
class CategoryFactory extends Factory
{
    protected $model = Category::class;

    public function definition(): array
    {
        return [
            'parent_id' => null,
            'slug' => Str::slug($this->faker->unique()->words(2, true)),
            'sort' => 0,
            'is_active' => true,
        ];
    }

    /**
     * Категория с русским названием.
     *
     * Без перевода Category::name() отдаёт slug, и в списках вместо
     * «Стройматериалы» появляется «stroymaterialy».
     */
    public function named(string $name): static
    {
        return $this->afterCreating(function (Category $category) use ($name): void {
            $category->translations()->firstOrCreate(['locale' => 'ru'], ['name' => $name]);
        });
    }

    public function child(Category $parent): static
    {
        return $this->state(['parent_id' => $parent->id]);
    }
}
