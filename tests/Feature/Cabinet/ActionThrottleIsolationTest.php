<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\Company;
use App\Models\Listing;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Storage;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * У каждого действия кабинета свой счётчик частоты.
 *
 * Без приставки ключа throttle у всех адресов пользователя был один
 * счётчик: автосохранение мастера (раз в 20 секунд) за три шага
 * расходовало лимит загрузки фото (30 в час), и на шаге «Фото и
 * документы» сайт отвечал «Слишком много действий подряд».
 */
class ActionThrottleIsolationTest extends TestCase
{
    use RefreshDatabase;

    #[Test]
    public function автосохранения_не_мешают_загрузке_фото(): void
    {
        Storage::fake('public');

        $company = Company::factory()->create();
        $user = User::factory()->for($company)->create(['email_verified_at' => now()]);
        $listing = Listing::factory()->create(['company_id' => $company->id, 'user_id' => $user->id]);

        // Больше лимита фото (30), но в пределах лимита автосохранения (60)
        foreach (range(1, 40) as $i) {
            $this->actingAs($user)
                ->postJson("/cabinet/listings/{$listing->id}/autosave", ['title' => "Черновик {$i}", 'step' => 3])
                ->assertOk();
        }

        $this->actingAs($user)
            ->withHeaders(['X-Inertia' => 'true'])
            ->from("/cabinet/listings/{$listing->id}/edit")
            ->post("/cabinet/listings/{$listing->id}/images", [
                'images' => [UploadedFile::fake()->image('photo.jpg', 1200, 900)],
            ])
            ->assertSessionHasNoErrors()
            ->assertSessionHas('success');

        $this->assertSame(1, $listing->images()->count());
    }
}
