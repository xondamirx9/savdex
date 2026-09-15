<?php

declare(strict_types=1);

namespace Database\Factories;

use App\Models\Refund;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends Factory<Refund>
 */
class RefundFactory extends Factory
{
    protected $model = Refund::class;

    public function definition(): array
    {
        return [
            'amount' => 429500,
            'currency' => 'UZS',
            'reason' => 'Оплата прошла дважды по вине шлюза',
            'status' => Refund::STATUS_REQUESTED,
        ];
    }
}
