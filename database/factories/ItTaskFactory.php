<?php

declare(strict_types=1);

namespace Database\Factories;

use App\Models\Company;
use App\Models\ItTask;
use Illuminate\Database\Eloquent\Factories\Factory;

/** @extends Factory<ItTask> */
class ItTaskFactory extends Factory
{
    protected $model = ItTask::class;

    public function definition(): array
    {
        return [
            'company_id' => Company::factory(),
            'title' => $this->faker->randomElement([
                'Разработать интернет-магазин стройматериалов',
                'Интеграция сайта с 1С и складом',
                'Мобильное приложение для дилеров',
                'Telegram-бот для приёма заявок',
            ]).' '.$this->faker->numberBetween(100, 999),
            'description' => $this->faker->realText(300),
            'service_type' => 'web',
            'stack' => ['Laravel', 'React'],
            'budget_type' => 'range',
            'budget_from' => 20_000_000,
            'budget_to' => 50_000_000,
            'currency' => 'UZS',
            'deadline_at' => now()->addDays(30),
            'status' => ItTask::STATUS_ACTIVE,
            'published_at' => now(),
        ];
    }

    public function closed(): static
    {
        return $this->state(['status' => ItTask::STATUS_CLOSED, 'closed_at' => now()]);
    }
}
