<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Resources\Listings\Pages\ListListings;
use App\Models\Company;
use App\Models\Listing;
use App\Models\User;
use App\Support\AdminAccess;
use Filament\Actions\Testing\TestAction;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Публикация загруженного объявления из админки.
 *
 * Загрузка из книги кладёт объявления в «На проверке» — на витрину
 * они попадают только кнопкой «Одобрить». Кнопка ставит срок и видна
 * лишь тем, кому положено модерировать: раньше её видел любой, кто
 * видит список, включая поддержку с правом только смотреть.
 */
class ListingApprovalTest extends TestCase
{
    use RefreshDatabase;

    private function admin(string $role): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => $role,
            'status' => 'active',
        ]);
    }

    private function pending(): Listing
    {
        return Listing::factory()->for(Company::factory())->create([
            'status' => Listing::STATUS_MODERATION,
            'source' => Listing::SOURCE_IMPORT,
            'published_at' => null,
            'expires_at' => null,
        ]);
    }

    #[Test]
    public function одобрение_публикует_и_ставит_срок(): void
    {
        $listing = $this->pending();

        Livewire::actingAs($this->admin(AdminAccess::MODERATOR))
            ->test(ListListings::class)
            ->callAction(TestAction::make('approve')->table($listing))
            ->assertHasNoActionErrors();

        $fresh = $listing->fresh();

        $this->assertSame(Listing::STATUS_ACTIVE, $fresh->status);
        $this->assertNotNull($fresh->published_at);
        $this->assertNotNull($fresh->expires_at);

        // Одобренное объявление видно на витрине
        $this->get('/listing/'.$fresh->slug)->assertOk();
    }

    #[Test]
    public function без_права_модерировать_кнопки_одобрить_нет(): void
    {
        $listing = $this->pending();

        // Поддержка видит объявления, но не публикует их
        Livewire::actingAs($this->admin(AdminAccess::SUPPORT))
            ->test(ListListings::class)
            ->assertActionHidden(TestAction::make('approve')->table($listing))
            ->assertActionHidden(TestAction::make('reject')->table($listing));

        $this->assertSame(Listing::STATUS_MODERATION, $listing->fresh()->status);
    }

    #[Test]
    public function непроверенное_на_витрине_не_показывается(): void
    {
        $listing = $this->pending();

        $this->get('/listing/'.$listing->slug)->assertNotFound();
        $this->get('/catalog')->assertOk()->assertDontSee($listing->title);
    }
}
