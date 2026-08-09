<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Resources\Companies\CompanyResource;
use App\Filament\Resources\Listings\ListingResource;
use App\Models\Company;
use App\Models\Listing;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Право удалять данные — только у суперадмина.
 *
 * Компании и объявления модератор видит: это его работа. Но удаление
 * не переопределялось, а Filament без политики разрешает всё — модератор
 * мог выделить полсотни компаний галочками и снести их вместе с
 * кошельками, подписками и оплаченными раскрытиями.
 */
class AdminDeletionRightsTest extends TestCase
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

    #[Test]
    public function модератор_не_удаляет_компании_и_объявления(): void
    {
        $this->actingAs($this->admin(User::ADMIN_MODERATOR));

        $company = Company::factory()->create();
        $listing = Listing::factory()->create();

        $this->assertFalse(CompanyResource::canDelete($company));
        $this->assertFalse(CompanyResource::canDeleteAny(), 'массовое удаление опаснее всего');
        $this->assertFalse(CompanyResource::canForceDelete($company));

        $this->assertFalse(ListingResource::canDelete($listing));
        $this->assertFalse(ListingResource::canDeleteAny());
        $this->assertFalse(ListingResource::canForceDelete($listing));
    }

    /** Модерация остаётся доступной: разделы он по-прежнему видит и правит. */
    #[Test]
    public function модератор_сохраняет_свои_права(): void
    {
        $this->actingAs($this->admin(User::ADMIN_MODERATOR));

        $this->assertTrue(CompanyResource::canViewAny());
        $this->assertTrue(ListingResource::canViewAny());
        $this->assertTrue(ListingResource::canEdit(Listing::factory()->create()));
    }

    #[Test]
    public function суперадмин_удалять_может(): void
    {
        $this->actingAs($this->admin(User::ADMIN_SUPERADMIN));

        $company = Company::factory()->create();
        $listing = Listing::factory()->create();

        $this->assertTrue(CompanyResource::canDelete($company));
        $this->assertTrue(CompanyResource::canForceDelete($company));
        $this->assertTrue(ListingResource::canDelete($listing));
        $this->assertTrue(ListingResource::canForceDelete($listing));
    }
}
