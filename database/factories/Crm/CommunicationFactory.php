<?php

declare(strict_types=1);

namespace Database\Factories\Crm;

use App\Models\Crm\Communication;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends Factory<Communication>
 */
class CommunicationFactory extends Factory
{
    protected $model = Communication::class;

    public function definition(): array
    {
        return [
            'type' => 'call',
            'happened_at' => now(),
            'summary' => 'Договорились о пробной партии',
        ];
    }
}
