<?php

declare(strict_types=1);

namespace Database\Factories;

use App\Models\Company;
use App\Models\Review;
use Illuminate\Database\Eloquent\Factories\Factory;

/** @extends Factory<Review> */
class ReviewFactory extends Factory
{
    protected $model = Review::class;

    public function definition(): array
    {
        $rating = $this->faker->numberBetween(3, 5);

        return [
            'company_id' => Company::factory(),
            'author_company_id' => Company::factory(),
            'rating' => $rating,
            'rating_description' => $rating,
            'rating_response' => $rating,
            'rating_deadlines' => $rating,
            'rating_quality' => $rating,
            'body' => $this->faker->realText(150),
            'deal_confirmed' => true,
            'status' => 'published',
        ];
    }
}
