<?php

declare(strict_types=1);

namespace Database\Factories\Support;

use App\Models\Support\Ticket;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends Factory<Ticket>
 */
class TicketFactory extends Factory
{
    protected $model = Ticket::class;

    public function definition(): array
    {
        return [
            'subject' => 'Не приходит письмо для подтверждения почты',
            'status' => Ticket::STATUS_OPEN,
            'channel' => 'form',
            'priority' => 'normal',
            'author_name' => 'Иван Петров',
            'author_email' => 'ivan@example.com',
        ];
    }
}
