<?php

declare(strict_types=1);

namespace Database\Factories;

use App\Models\City;
use App\Models\Company;
use App\Models\Country;
use Illuminate\Database\Eloquent\Factories\Factory;

/**
 * @extends Factory<Company>
 */
class CompanyFactory extends Factory
{
    protected $model = Company::class;

    public function definition(): array
    {
        return [
            'name' => 'ООО «'.$this->faker->unique()->company().'»',
            'tin' => (string) $this->faker->unique()->numberBetween(100_000_000, 999_999_999),
            'type' => $this->faker->randomElement(['manufacturer', 'importer', 'distributor', 'trading', 'services']),
            'primary_role' => 'both',
            'verification_level' => Company::VERIFICATION_NONE,
            'rating' => $this->faker->randomFloat(2, 3.5, 5),
            'reviews_count' => $this->faker->numberBetween(0, 60),
            'completed_deals_count' => $this->faker->numberBetween(0, 120),
            'response_time_hours' => $this->faker->numberBetween(1, 24),
            'status' => Company::STATUS_ACTIVE,

            /*
             * Страна и город создаются лениво: большинству тестов
             * они не нужны, а лишние вставки замедляют прогон.
             *
             * Код строго в нижнем регистре — как в GeoSeeder. С 'UZ'
             * поиск не находил существующую страну и заводил вторую:
             * в списке при регистрации было два «Узбекистана».
             */
            'country_id' => fn () => Country::firstOrCreate(
                ['code' => 'uz'],
                ['phone_code' => '998', 'currency_code' => 'UZS', 'is_active' => true],
            )->id,
            'city_id' => fn (array $attrs) => City::firstOrCreate(
                ['country_id' => $attrs['country_id'], 'slug' => 'tashkent'],
                ['is_active' => true],
            )->id,
        ];
    }

    public function verified(): static
    {
        return $this->state(['verification_level' => Company::VERIFICATION_COMPANY, 'verified_at' => now()]);
    }

    public function blocked(): static
    {
        return $this->state(['status' => Company::STATUS_BLOCKED, 'blocked_at' => now()]);
    }
}
