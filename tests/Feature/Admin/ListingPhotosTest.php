<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Resources\Listings\Pages\EditListing;
use App\Models\Category;
use App\Models\Listing;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Storage;
use Livewire\Features\SupportTesting\Testable;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Фотографии объявления в админке.
 *
 * До этого снимки добавлялись только из кабинета владельца, а в чужой
 * кабинет администратор попасть не может: демонстрационные объявления
 * и карточки, которые ведёт сама площадка, оставались без фотографий.
 */
class ListingPhotosTest extends TestCase
{
    use RefreshDatabase;

    private function admin(): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => User::ADMIN_SUPERADMIN,
            'status' => 'active',
        ]);
    }

    private function listing(): Listing
    {
        $category = Category::factory()->named('Стройматериалы')->create();

        return Listing::factory()->create([
            'category_id' => $category->id,
            'status' => Listing::STATUS_ACTIVE,
        ]);
    }

    private function edit(Listing $listing): Testable
    {
        return Livewire::actingAs($this->admin())
            ->test(EditListing::class, ['record' => $listing->getRouteKey()]);
    }

    #[Test]
    public function фотография_добавляется_из_админки(): void
    {
        Storage::fake('public');

        $listing = $this->listing();

        $this->edit($listing)
            ->fillForm(['gallery' => [UploadedFile::fake()->image('cement.jpg', 1600, 1200)]])
            ->call('save')
            ->assertHasNoFormErrors();

        $images = $listing->fresh()->images()->orderBy('sort')->get();

        $this->assertCount(1, $images);
        Storage::disk('public')->assertExists($images->first()->path);
        $this->assertStringContainsString('storage/', $images->first()->url());
    }

    /** Порядок задаёт обложку: первая фотография показывается в каталоге. */
    #[Test]
    public function порядок_фотографий_сохраняется(): void
    {
        Storage::fake('public');

        $listing = $this->listing();

        $this->edit($listing)
            ->fillForm(['gallery' => [
                UploadedFile::fake()->image('first.jpg'),
                UploadedFile::fake()->image('second.jpg'),
            ]])
            ->call('save')
            ->assertHasNoFormErrors();

        $sorted = $listing->fresh()->images()->orderBy('sort')->pluck('sort')->all();

        $this->assertSame([0, 1], $sorted);
    }

    /** Снятая фотография исчезает вместе с файлом, а не остаётся на диске. */
    #[Test]
    public function снятая_фотография_удаляется_с_диском(): void
    {
        Storage::fake('public');

        $listing = $this->listing();

        $this->edit($listing)
            ->fillForm(['gallery' => [UploadedFile::fake()->image('one.jpg')]])
            ->call('save');

        $path = $listing->fresh()->images()->firstOrFail()->path;
        Storage::disk('public')->assertExists($path);

        $this->edit($listing->fresh())
            ->fillForm(['gallery' => []])
            ->call('save')
            ->assertHasNoFormErrors();

        $this->assertCount(0, $listing->fresh()->images);
        Storage::disk('public')->assertMissing($path);
    }

    /** Правка объявления без трогания фотографий их не теряет. */
    #[Test]
    public function правка_описания_не_стирает_фотографии(): void
    {
        Storage::fake('public');

        $listing = $this->listing();

        $this->edit($listing)
            ->fillForm(['gallery' => [UploadedFile::fake()->image('keep.jpg')]])
            ->call('save');

        $this->assertCount(1, $listing->fresh()->images);

        $this->edit($listing->fresh())
            ->fillForm(['title' => 'Цемент М400 навалом и в мешках 50 кг'])
            ->call('save')
            ->assertHasNoFormErrors();

        $this->assertCount(1, $listing->fresh()->images);
        $this->assertSame('Цемент М400 навалом и в мешках 50 кг', $listing->fresh()->title);
    }
}
