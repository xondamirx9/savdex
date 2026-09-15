<?php

declare(strict_types=1);

namespace Database\Factories\Crm;

use App\Models\Crm\Deal;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends Factory<Deal>
 */
class DealFactory extends Factory
{
    protected $model = Deal::class;

    public function definition(): array
    {
        return [
            'title' => 'Поставка цемента М400',
            'amount' => 46386000,
            'currency' => 'UZS',
            'stage' => Deal::STAGE_NEW,
        ];
    }
}
