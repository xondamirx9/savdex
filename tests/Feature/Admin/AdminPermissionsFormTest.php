<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Resources\Users\Pages\EditUser;
use App\Models\User;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Выдача личных прав через форму пользователя.
 *
 * Роль и добавки лежат в разных колонках, а на форме — рядом, причём
 * добавки пишутся во вложенный путь admin_permissions.grant. Тест
 * проверяет именно стык: что галочка доезжает до колонки и обратно,
 * и что роль при этом не меняется.
 */
class AdminPermissionsFormTest extends TestCase
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
    public function суперадмин_выдаёт_личное_право_через_форму(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPERADMIN));

        $target = $this->admin(AdminAccess::ADMIN);

        $this->assertFalse($target->hasAdminAbility('payments.view'));

        Livewire::test(EditUser::class, ['record' => $target->getRouteKey()])
            ->fillForm(['admin_permissions' => ['grant' => ['payments.view'], 'revoke' => []]])
            ->call('save')
            ->assertHasNoFormErrors();

        $target->refresh();

        $this->assertSame(['grant' => ['payments.view'], 'revoke' => []], $target->admin_permissions);
        $this->assertTrue($target->hasAdminAbility('payments.view'));
        $this->assertSame(AdminAccess::ADMIN, $target->admin_role, 'роль меняться не должна');
    }

    #[Test]
    public function выданное_право_возвращается_в_форму(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPERADMIN));

        $target = $this->admin(AdminAccess::ADMIN);
        $target->forceFill(['admin_permissions' => ['grant' => ['payments.view']]])->save();

        Livewire::test(EditUser::class, ['record' => $target->getRouteKey()])
            // revoke приходит пустым списком: чекбоксы без отметок — это [],
            // а не отсутствие ключа
            ->assertFormSet(['admin_permissions' => ['grant' => ['payments.view'], 'revoke' => []]]);
    }

    /**
     * Администратор не видит полей выдачи доступа.
     *
     * Скрытое поле не приезжает в состояние формы, поэтому сохранение
     * чужой карточки не может ни поднять роль, ни выдать право — даже
     * если значения подставить в запрос руками.
     */
    #[Test]
    public function администратор_не_меняет_роль_чужой_карточки(): void
    {
        $this->actingAs($this->admin(AdminAccess::ADMIN));

        $target = $this->admin(AdminAccess::MODERATOR);

        Livewire::test(EditUser::class, ['record' => $target->getRouteKey()])
            ->assertFormFieldHidden('admin_role')
            ->assertFormFieldHidden('is_admin')
            ->fillForm(['name' => 'Новое имя'])
            ->call('save')
            ->assertHasNoFormErrors();

        $target->refresh();

        $this->assertSame('Новое имя', $target->name);
        $this->assertSame(AdminAccess::MODERATOR, $target->admin_role, 'роль осталась прежней');
    }
}
