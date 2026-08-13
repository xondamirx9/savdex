<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Pages\Invoices;
use App\Filament\Resources\Broadcasts\BroadcastResource;
use App\Filament\Resources\Categories\CategoryResource;
use App\Filament\Resources\Companies\CompanyResource;
use App\Filament\Resources\CompanyTypes\CompanyTypeResource;
use App\Filament\Resources\Listings\ListingResource;
use App\Filament\Resources\Plans\PlanResource;
use App\Filament\Resources\Subscriptions\SubscriptionResource;
use App\Filament\Resources\Users\UserResource;
use App\Models\User;
use Filament\Facades\Filament;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Роли в админке (§6.3 ТЗ).
 *
 * Проверяется не видимость пунктов меню, а право открыть раздел:
 * скрытая ссылка ничего не защищает — адрес вводится руками
 * (NEG-26e из QA.md).
 */
class AdminAccessTest extends TestCase
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
    public function обычный_пользователь_в_панель_не_попадает(): void
    {
        $user = User::factory()->create(['is_admin' => false]);

        $this->assertFalse($user->canAccessPanel(Filament::getPanel('admin')));
    }

    /** Заблокированный администратор — тоже не администратор. */
    #[Test]
    public function заблокированный_админ_в_панель_не_попадает(): void
    {
        $user = $this->admin(User::ADMIN_SUPERADMIN);
        $user->forceFill(['status' => 'blocked'])->save();

        $this->assertFalse($user->fresh()->canAccessPanel(Filament::getPanel('admin')));
    }

    #[Test]
    public function модератор_видит_модерацию(): void
    {
        $this->actingAs($this->admin(User::ADMIN_MODERATOR));

        $this->assertTrue(ListingResource::canViewAny());
        $this->assertTrue(CompanyResource::canViewAny());
    }

    /**
     * @return list<array{class-string}>
     */
    public static function разделыСуперадмина(): array
    {
        return [
            [UserResource::class],
            [CategoryResource::class],
            [BroadcastResource::class],
            [CompanyTypeResource::class],
            [PlanResource::class],
            [SubscriptionResource::class],
        ];
    }

    #[Test]
    #[DataProvider('разделыСуперадмина')]
    public function модератор_не_видит_разделы_суперадмина(string $resource): void
    {
        $this->actingAs($this->admin(User::ADMIN_MODERATOR));

        $this->assertFalse($resource::canViewAny(), "{$resource} не должен быть доступен модератору");
    }

    #[Test]
    #[DataProvider('разделыСуперадмина')]
    public function суперадмин_видит_всё(string $resource): void
    {
        $this->actingAs($this->admin(User::ADMIN_SUPERADMIN));

        $this->assertTrue($resource::canViewAny());
    }

    /**
     * Роль по умолчанию — модератор: администратор без явно указанной
     * роли не должен случайно получить право менять тарифы и выгружать базу.
     */
    #[Test]
    public function админ_без_роли_считается_модератором(): void
    {
        $user = $this->admin(User::ADMIN_MODERATOR);
        $user->forceFill(['admin_role' => null])->save();

        $this->assertFalse($user->fresh()->isSuperadmin());
        $this->assertSame('Модератор', $user->fresh()->adminRoleLabel());
    }

    #[Test]
    public function суперадмин_является_и_модератором(): void
    {
        $this->assertTrue($this->admin(User::ADMIN_SUPERADMIN)->isModerator());
    }

    /**
     * Модератор не может ни создать, ни отредактировать пользователя.
     *
     * canViewAny прячет раздел из меню, но страницы create/edit
     * авторизуются через canCreate/canEdit — без этой проверки
     * модератор по прямой ссылке /admin/users/create заводил себе
     * суперадмина. Проверяем именно право на действие, а не видимость.
     */
    #[Test]
    public function модератор_не_создаёт_и_не_правит_пользователей(): void
    {
        $victim = User::factory()->create();
        $this->actingAs($this->admin(User::ADMIN_MODERATOR));

        $this->assertFalse(UserResource::canCreate(), 'модератор не должен создавать пользователей');
        $this->assertFalse(UserResource::canEdit($victim), 'модератор не должен править пользователей');
        $this->assertFalse(UserResource::canDelete($victim), 'модератор не должен удалять пользователей');
    }

    #[Test]
    public function суперадмин_создаёт_и_правит_пользователей(): void
    {
        $victim = User::factory()->create();
        $this->actingAs($this->admin(User::ADMIN_SUPERADMIN));

        $this->assertTrue(UserResource::canCreate());
        $this->assertTrue(UserResource::canEdit($victim));
    }

    /**
     * Счета и подтверждение оплат — только суперадмину.
     *
     * Страница активирует подписки и зачисляет кредиты; без гейта
     * модератор по прямой ссылке подтверждал бы оплату без денег (NEG-26e).
     */
    #[Test]
    public function модератор_не_открывает_счета_и_оплаты(): void
    {
        $this->actingAs($this->admin(User::ADMIN_MODERATOR));

        $this->assertFalse(Invoices::canAccess());
    }

    #[Test]
    public function суперадмин_открывает_счета_и_оплаты(): void
    {
        $this->actingAs($this->admin(User::ADMIN_SUPERADMIN));

        $this->assertTrue(Invoices::canAccess());
    }
}
