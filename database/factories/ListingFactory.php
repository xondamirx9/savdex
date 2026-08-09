<?php

declare(strict_types=1);

namespace Database\Factories;

use App\Models\Category;
use App\Models\Company;
use App\Models\Listing;
use Illuminate\Database\Eloquent\Factories\Factory;

/** @extends Factory<Listing> */
class ListingFactory extends Factory
{
    protected $model = Listing::class;

    public function definition(): array
    {
        $title = $this->faker->randomElement([
            'Цемент М400 навалом',
            'Щебень фракция 5-20',
            'Арматура А500С',
            'Кирпич керамический М150',
            'Песок карьерный мытый',
        ]).' '.$this->faker->numberBetween(100, 999);

        return [
            'company_id' => Company::factory(),
            /*
             * Категория создаётся лениво: у настоящего объявления она
             * есть всегда — мастер публикации без неё не пропускает.
             * Фабрика оставляла null, и тесты работали с объявлением,
             * которого в базе не бывает.
             */
            'category_id' => fn () => Category::query()->where('is_active', true)->value('id')
                ?? Category::factory()->named('Стройматериалы')->create()->id,
            'type' => Listing::TYPE_SUPPLY,
            'title' => $title,
            'description' => $this->faker->realText(200),
            'price' => $this->faker->numberBetween(100_000, 5_000_000),
            'currency' => 'UZS',
            'unit' => 'т',
            'status' => Listing::STATUS_ACTIVE,
            'published_at' => now()->subDays($this->faker->numberBetween(1, 60)),
            'expires_at' => now()->addDays($this->faker->numberBetween(10, 90)),
            'impressions_count' => $this->faker->numberBetween(0, 2000),
            'views_count' => $this->faker->numberBetween(0, 300),
            'unlocks_count' => $this->faker->numberBetween(0, 20),
        ];
    }

    public function configure(): static
    {
        // Адрес строится из заголовка и id, а id известен только
        // после сохранения — поэтому в afterCreating
        return $this->afterCreating(function (Listing $listing): void {
            if (blank($listing->slug)) {
                $listing->slug = Listing::makeSlug($listing->title, $listing->id);
                $listing->save();
            }
        });
    }

    public function draft(): static
    {
        return $this->state(['status' => Listing::STATUS_DRAFT, 'published_at' => null, 'expires_at' => null]);
    }
}
