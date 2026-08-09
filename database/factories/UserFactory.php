<?php

namespace Database\Factories;

use App\Models\User;
use Illuminate\Database\Eloquent\Factories\Factory;
use Illuminate\Support\Facades\Hash;
use Illuminate\Support\Str;

/**
 * @extends Factory<User>
 */
class UserFactory extends Factory
{
    /**
     * The current password being used by the factory.
     */
    protected static ?string $password;

    /**
     * Define the model's default state.
     *
     * @return array<string, mixed>
     */
    public function definition(): array
    {
        return [
            'name' => fake()->name(),
            'email' => fake()->unique()->safeEmail(),
            'email_verified_at' => now(),
            'password' => static::$password ??= Hash::make('password'),
            'remember_token' => Str::random(10),

            /*
             * Поля со значениями по умолчанию в схеме задаются явно.
             *
             * Иначе созданный фабрикой объект отличается от того же
             * объекта, перечитанного из базы: в памяти status и
             * must_change_password остаются null, и canAct() молча
             * возвращает false. В тестах через actingAs($user) в auth
             * попадает именно этот неполный объект — и проверка прав
             * ведёт себя не так, как в бою.
             */
            'status' => 'active',
            'must_change_password' => false,
            'company_role' => User::ROLE_OWNER,
        ];
    }

    /**
     * Indicate that the model's email address should be unverified.
     */
    public function unverified(): static
    {
        return $this->state(fn (array $attributes) => [
            'email_verified_at' => null,
        ]);
    }
}
