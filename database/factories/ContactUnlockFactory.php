<?php

declare(strict_types=1);

namespace Database\Factories;

use App\Models\Company;
use App\Models\ContactUnlock;
use Illuminate\Database\Eloquent\Factories\Factory;

/** @extends Factory<ContactUnlock> */
class ContactUnlockFactory extends Factory
{
    protected $model = ContactUnlock::class;

    public function definition(): array
    {
        return [
            'company_id' => Company::factory(),
            'target_company_id' => Company::factory(),
            'credits_spent' => 1,
            'status' => 'new',
        ];
    }
}
