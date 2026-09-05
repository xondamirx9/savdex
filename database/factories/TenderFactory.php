<?php

declare(strict_types=1);

namespace Database\Factories;

use App\Models\Category;
use App\Models\Tender;
use Illuminate\Database\Eloquent\Factories\Factory;

/** @extends Factory<Tender> */
class TenderFactory extends Factory
{
    protected $model = Tender::class;

    public function definition(): array
    {
        $title = $this->faker->randomElement([
            'Поставка цемента М400 для строительства школы',
            'Закупка хлопчатобумажной пряжи 30/1',
            'Поставка металлопроката для моста',
            'Закупка упаковочной плёнки',
            'Поставка офисной мебели',
        ]).' '.$this->faker->numberBetween(100, 999);

        return [
            'title' => $title,
            'description' => $this->faker->realText(300),
            'customer' => $this->faker->randomElement(['ГУП «Тошкент шахар курилиш»', 'АО «Узбекнефтегаз»', 'ООО «Андижан текстиль»']),
            'category_id' => fn () => Category::query()->where('is_active', true)->value('id')
                ?? Category::factory()->named('Стройматериалы')->create()->id,
            'location' => 'Ташкент',
            'budget' => $this->faker->numberBetween(10_000_000, 900_000_000),
            'currency' => 'UZS',
            'deadline_at' => now()->addDays($this->faker->numberBetween(5, 45)),
            'status' => Tender::STATUS_PUBLISHED,
            'published_at' => now()->subDays($this->faker->numberBetween(0, 10)),
        ];
    }

    public function draft(): static
    {
        return $this->state(['status' => Tender::STATUS_DRAFT, 'published_at' => null]);
    }

    public function closed(): static
    {
        return $this->state(['deadline_at' => now()->subDays(3)]);
    }
}
