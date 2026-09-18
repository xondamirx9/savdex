<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Resources\Listings\Pages\ListListings;
use App\Jobs\TranslateListing;
use App\Models\Company;
use App\Models\Listing;
use App\Models\User;
use App\Support\AdminAccess;
use Filament\Actions\Testing\TestAction;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Queue;
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

    /**
     * Загружает книги роль admin, а права модерировать у неё нет.
     * Загруженное она обязана уметь опубликовать сама — иначе
     * загружает то, что повесит в «На проверке» до прихода модератора.
     */
    #[Test]
    public function загрузивший_публикует_загруженное_без_права_модерировать(): void
    {
        $listing = $this->pending();

        Livewire::actingAs($this->admin(AdminAccess::ADMIN))
            ->test(ListListings::class)
            ->callAction(TestAction::make('approve')->table($listing))
            ->assertHasNoActionErrors();

        $this->assertSame(Listing::STATUS_ACTIVE, $listing->fresh()->status);

        // А написанное в кабинете — нет: это уже модерация
        $cabinet = Listing::factory()->for(Company::factory())->create([
            'status' => Listing::STATUS_MODERATION,
            'source' => Listing::SOURCE_CABINET,
        ]);

        Livewire::actingAs($this->admin(AdminAccess::ADMIN))
            ->test(ListListings::class)
            ->assertActionHidden(TestAction::make('approve')->table($cabinet));
    }

    /**
     * Книга дала английский, остальных языков нет: одобрение должно
     * позвать машинный перевод за недостающими, а не считать, что раз
     * переводы «есть», добирать нечего.
     */
    #[Test]
    public function одобрение_с_частью_языков_запускает_добор_перевода(): void
    {
        config()->set('services.machine_translation.enabled', true);
        Queue::fake();

        $listing = $this->pending();
        $listing->forceFill(['title_i18n' => ['en' => 'Ceramic brick M150']])->save();

        Queue::assertNothingPushed();

        Livewire::actingAs($this->admin(AdminAccess::MODERATOR))
            ->test(ListListings::class)
            ->callAction(TestAction::make('approve')->table($listing));

        Queue::assertPushed(TranslateListing::class, fn (TranslateListing $job): bool => $job->listingId === $listing->id);
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
