<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\Company;
use App\Models\Listing;
use App\Models\User;
use Database\Seeders\PlanSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Ограничение частоты откликов и его лицо для человека.
 *
 * Упор в throttle уводил на отдельную страницу ошибки — с потерей
 * набранного текста, а в вечно открытой вкладке она к тому же
 * рисовалась пустой. Теперь превышение возвращает на ту же страницу
 * с подсказкой под формой.
 */
class ChatThrottleTest extends TestCase
{
    use RefreshDatabase;

    #[Test]
    public function превышение_лимита_возвращает_ошибку_под_форму(): void
    {
        $this->seed(PlanSeeder::class);

        $listing = Listing::factory()->create([
            'company_id' => Company::factory()->create()->id,
            'status' => Listing::STATUS_ACTIVE,
            'published_at' => now()->subDay(),
        ]);
        $buyer = User::factory()->for(Company::factory())->create(['email_verified_at' => now()]);

        $response = null;

        // Лимит — 60 в час; 61-я попытка обязана упереться
        foreach (range(1, 61) as $i) {
            $response = $this->actingAs($buyer)
                ->from("/listing/{$listing->slug}")
                ->withHeaders(['X-Inertia' => 'true'])
                ->post("/listing/{$listing->id}/respond", ['body' => "Сообщение {$i}"]);
        }

        $response
            ->assertRedirect("/listing/{$listing->slug}")
            ->assertSessionHasErrors('body');
    }
}
