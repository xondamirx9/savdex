<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Resources\Listings\Pages\EditListing;
use App\Filament\Resources\Listings\RelationManagers\ImagesRelationManager;
use App\Models\Company;
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
 * Фотографии чужих объявлений — из админки.
 *
 * Администратор правит любые объявления целиком: не только тексты
 * (это умела форма), но и снимки — заменить, удалить, назначить
 * обложку. Обработка обязана совпадать с пользовательской загрузкой:
 * фото из админки не должно отличаться ни форматом, ни миниатюрой.
 */
class ListingImagesAdminTest extends TestCase
{
    use RefreshDatabase;

    private User $admin;

    private Listing $listing;

    protected function setUp(): void
    {
        parent::setUp();

        Storage::fake('public');

        $this->admin = User::factory()->create([
            'is_admin' => true,
            'admin_role' => User::ADMIN_SUPERADMIN,
            'status' => 'active',
        ]);

        // Объявление постороннего пользователя — суть «админа бога»
        $this->listing = Listing::factory()->create([
            'company_id' => Company::factory()->create()->id,
            'status' => Listing::STATUS_ACTIVE,
            'published_at' => now()->subDay(),
        ]);
    }

    private function manager(): Testable
    {
        return Livewire::actingAs($this->admin)->test(ImagesRelationManager::class, [
            'ownerRecord' => $this->listing,
            'pageClass' => EditListing::class,
        ]);
    }

    #[Test]
    public function админ_загружает_фото_в_чужое_объявление(): void
    {
        $this->manager()
            ->callTableAction('upload', data: [
                'photos' => [UploadedFile::fake()->image('photo.jpg', 900, 700)],
            ])
            ->assertHasNoTableActionErrors();

        $image = $this->listing->images()->firstOrFail();

        // Пережато в webp с миниатюрой — как при загрузке владельцем
        $this->assertStringEndsWith('.webp', $image->path);
        Storage::disk('public')->assertExists($image->path);
        Storage::disk('public')->assertExists($image->thumb_path);
    }

    #[Test]
    public function админ_назначает_обложку_и_удаляет_фото(): void
    {
        $first = $this->listing->images()->create(['path' => 'listings/a.webp', 'thumb_path' => 'listings/at.webp', 'sort' => 0]);
        $second = $this->listing->images()->create(['path' => 'listings/b.webp', 'thumb_path' => 'listings/bt.webp', 'sort' => 1]);
        Storage::disk('public')->put('listings/b.webp', 'x');
        Storage::disk('public')->put('listings/bt.webp', 'x');

        $this->manager()->callTableAction('cover', $second);

        $this->assertSame(0, $second->fresh()->sort);
        $this->assertSame(1, $first->fresh()->sort);

        $this->manager()->callTableAction('remove', $second);

        $this->assertNull($second->fresh());
        Storage::disk('public')->assertMissing('listings/b.webp');
    }
}
