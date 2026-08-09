<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Resources\CompanyTypes\Pages\ListCompanyTypes;
use App\Filament\Resources\Users\Pages\ListUsers;
use App\Filament\Resources\Users\UserResource;
use App\Models\Company;
use App\Models\CompanyType;
use App\Models\User;
use App\Models\UserNotification;
use Filament\Actions\Testing\TestAction;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Действия админки, которые нельзя проверить правами: они меняют
 * данные, а не только видимость раздела.
 */
class AdminActionsTest extends TestCase
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

    /**
     * Ручное подтверждение почты нужно там, где письмо не доходит:
     * корпоративная почта рубит рассылки, домен не прогрет.
     */
    #[Test]
    public function суперадмин_подтверждает_почту_вручную(): void
    {
        $this->actingAs($this->admin(User::ADMIN_SUPERADMIN));

        $company = Company::factory()->create();
        $user = User::factory()->create([
            'company_id' => $company->id,
            'email_verified_at' => null,
        ]);

        Livewire::test(ListUsers::class)
            ->callAction(TestAction::make('verifyEmail')->table($user));

        $this->assertNotNull($user->fresh()->email_verified_at);
        $this->assertTrue(
            UserNotification::where('user_id', $user->id)->exists(),
            'человек должен узнать, что доступ открыт',
        );
    }

    /**
     * Подтверждение снимает ограничение на публикацию и раскрытие
     * контактов — то есть открывает деньги. Модератору не даём.
     *
     * Раздел пользователей для него закрыт целиком, поэтому проверяем
     * ответ страницы, а не видимость кнопки: до кнопки он не дойдёт.
     */
    #[Test]
    public function модератор_подтвердить_почту_не_может(): void
    {
        $this->actingAs($this->admin(User::ADMIN_MODERATOR));

        $user = User::factory()->create(['email_verified_at' => null]);

        $this->get(UserResource::getUrl('index'))->assertForbidden();

        $this->assertNull($user->fresh()->email_verified_at);
    }

    /** Подтверждённой почте кнопка не нужна — подтверждать нечего. */
    #[Test]
    public function подтверждённой_почте_кнопка_не_показывается(): void
    {
        $this->actingAs($this->admin(User::ADMIN_SUPERADMIN));

        $user = User::factory()->create(['email_verified_at' => now()]);

        Livewire::test(ListUsers::class)
            ->assertActionHidden(TestAction::make('verifyEmail')->table($user));
    }

    /**
     * Тип с компаниями удалять нельзя: у них останется ссылка на
     * несуществующее значение, и в карточке вместо типа появится код.
     */
    #[Test]
    public function используемый_тип_компании_не_удаляется(): void
    {
        $this->actingAs($this->admin(User::ADMIN_SUPERADMIN));

        $type = CompanyType::where('code', 'manufacturer')->firstOrFail();
        Company::factory()->create(['type' => 'manufacturer']);

        Livewire::test(ListCompanyTypes::class)
            ->callAction(TestAction::make('delete')->table($type));

        $this->assertModelExists($type);
    }

    /** Справочник наполнен миграцией: пустой список сломал бы регистрацию. */
    #[Test]
    public function справочник_типов_отдаёт_названия_для_формы(): void
    {
        $options = Company::typeOptions();

        $this->assertArrayHasKey('manufacturer', $options);
        $this->assertSame('Производитель', $options['manufacturer']);
    }

    /** Выключенный тип исчезает из выбора, но остаётся у тех, кто его выбрал. */
    #[Test]
    public function выключенный_тип_не_предлагается_но_подписывается(): void
    {
        CompanyType::where('code', 'service')->update(['is_active' => false]);

        $company = Company::factory()->create(['type' => 'service']);

        $this->assertArrayNotHasKey('service', Company::typeOptions());
        $this->assertSame('service', $company->typeLabel(), 'запасной вариант — сам код, а не пустая строка');
    }
}
