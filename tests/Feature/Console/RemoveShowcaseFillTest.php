<?php

declare(strict_types=1);

namespace Tests\Feature\Console;

use App\Models\Company;
use App\Models\Listing;
use App\Models\ListingImage;
use Database\Seeders\DatabaseSeeder;
use Database\Seeders\ShowcaseSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Storage;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Миграция remove_showcase_fill убирает то, что дописал ShowcaseSeeder,
 * и не трогает написанное и загруженное самими компаниями.
 */
class RemoveShowcaseFillTest extends TestCase
{
    use RefreshDatabase;

    #[Test]
    public function сгенерированное_убрано_своё_на_месте(): void
    {
        Storage::fake('public');
        $this->seed(DatabaseSeeder::class);

        $empty = Company::factory()->create(['description' => null]);
        $own = Company::factory()->create(['description' => 'Своё описание компании, написанное руками.']);
        $bare = Listing::factory()->create(['company_id' => $empty->id]);
        $photographed = Listing::factory()->create(['company_id' => $own->id]);
        $photo = ListingImage::create(['listing_id' => $photographed->id, 'path' => 'listings/'.$photographed->id.'/photo.jpg', 'sort' => 0]);

        $this->seed(ShowcaseSeeder::class);

        $this->assertNotNull($empty->fresh()->description, 'сидер дописал описание');
        $this->assertSame(3, $bare->images()->count(), 'и нарисовал картинки');

        // Компания переписала сгенерированное своими словами — это уже её текст
        $edited = Company::factory()->create(['description' => null]);
        $this->seed(ShowcaseSeeder::class);
        $edited->forceFill(['description' => 'Производственная компания из Ташкента. Делаем своё и отвечаем сами.'])->save();

        $migration = require database_path('migrations/2026_09_29_130000_remove_showcase_fill.php');
        $migration->up();

        $this->assertNull($empty->fresh()->description);
        $this->assertSame('Своё описание компании, написанное руками.', $own->fresh()->description);
        $this->assertNotNull($edited->fresh()->description);
        $this->assertSame(0, $bare->images()->count());
        $this->assertSame(0, ListingImage::where('path', 'like', '%showcase%')->count());
        Storage::disk('public')->assertMissing('listings/'.$bare->id.'/showcase-0.svg');
        $this->assertNotNull($photo->fresh());
    }
}
