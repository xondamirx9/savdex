<?php

declare(strict_types=1);

namespace Database\Factories\Crm;

use App\Models\Crm\Task;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends Factory<Task>
 */
class TaskFactory extends Factory
{
    protected $model = Task::class;

    public function definition(): array
    {
        return [
            'title' => 'Позвонить и уточнить объём',
            'due_at' => now()->addDay(),
        ];
    }
}
