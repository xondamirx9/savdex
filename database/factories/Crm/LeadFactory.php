<?php

declare(strict_types=1);

namespace Database\Factories\Crm;

use App\Models\Crm\Lead;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends Factory<Lead>
 */
class LeadFactory extends Factory
{
    protected $model = Lead::class;

    public function definition(): array
    {
        return [
            'title' => 'Ищет поставщика цемента',
            'source' => 'site',
            'status' => Lead::STATUS_NEW,
            'contact_name' => 'Иван Петров',
            'contact_phone' => '+998901234567',
        ];
    }
}
