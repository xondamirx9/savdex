<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Resources\Listings\Pages\ListListings;
use App\Models\Listing;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;
use Throwable;

/**
 * Массовое удаление объявлений в админке.
 *
 * Право удалять — только у суперадмина (докблок ListingResource),
 * но canDeleteAny ресурса массовые действия не прячет: без явного
 * visible() модератор удалял записи пачкой. Здесь же — скрытие
 * пустых авточерновиков: их создаёт сам мастер, и «удаление» таких
 * строк выглядело неработающим — кабинет тут же заводил новые.
 */
class AdminBulkDeleteTest extends TestCase
{
    use RefreshDatabase;

    private function admin(string $role): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => $role,
            'email_verified_at' => now(),
        ]);
    }

    #[Test]
    public function суперадмин_удаляет_объявления_массово(): void
    {
        $this->actingAs($this->admin(User::ADMIN_SUPERADMIN));

        $listings = Listing::factory()->count(2)->create();

        Livewire::test(ListListings::class)
            ->callTableBulkAction('delete', $listings);

        foreach ($listings as $listing) {
            $this->assertSoftDeleted('listings', ['id' => $listing->id]);
        }
    }

    #[Test]
    public function модератору_массовое_удаление_недоступно(): void
    {
        $this->actingAs($this->admin(User::ADMIN_MODERATOR));

        $listings = Listing::factory()->count(2)->create();

        try {
            Livewire::test(ListListings::class)->callTableBulkAction('delete', $listings);
        } catch (Throwable) {
            // Скрытое действие не вызывается — это и есть ожидаемое поведение
        }

        $this->assertSame(2, Listing::count());
        $this->assertSame(0, Listing::onlyTrashed()->count());
    }

    /** Пустой авточерновик мастера — не контент, в списке ему не место. */
    #[Test]
    public function пустые_черновики_скрыты_из_списка(): void
    {
        $this->actingAs($this->admin(User::ADMIN_SUPERADMIN));

        $empty = Listing::factory()->create(['status' => Listing::STATUS_DRAFT, 'title' => '']);
        $real = Listing::factory()->create(['status' => Listing::STATUS_DRAFT, 'title' => 'Настоящий черновик']);

        Livewire::test(ListListings::class)
            ->assertCanSeeTableRecords([$real])
            ->assertCanNotSeeTableRecords([$empty]);
    }
}
