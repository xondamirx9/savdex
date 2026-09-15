<?php

declare(strict_types=1);

namespace Database\Factories\Crm;

use App\Models\Crm\Contact;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends Factory<Contact>
 */
class ContactFactory extends Factory
{
    protected $model = Contact::class;

    public function definition(): array
    {
        return [
            'name' => 'Иван Петров',
            'position' => 'снабженец',
            'phone' => '+998901234567',
        ];
    }
}
