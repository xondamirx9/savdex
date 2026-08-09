<?php

declare(strict_types=1);

namespace Tests\Feature\Auth;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Hash;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Смена пароля, выданного администратором вручную (§6.3 ТЗ).
 *
 * До ручного прохода экран был заглушкой, а обработчика сохранения
 * не существовало вовсе: пользователь с флагом must_change_password
 * попадал в тупик, из которого не мог выйти.
 */
class ForcePasswordTest extends TestCase
{
    use RefreshDatabase;

    #[Test]
    public function форма_открывается_при_выставленном_флаге(): void
    {
        $user = User::factory()->create(['must_change_password' => true]);

        $this->actingAs($user)
            ->get('/password/change')
            ->assertOk()
            ->assertInertia(fn (AssertableInertia $page) => $page->component('auth/ForcePassword'));
    }

    #[Test]
    public function без_флага_отправляет_в_кабинет(): void
    {
        $this->actingAs(User::factory()->create())
            ->get('/password/change')
            ->assertRedirect('/cabinet');
    }

    #[Test]
    public function пароль_сохраняется_и_флаг_снимается(): void
    {
        $user = User::factory()->create(['must_change_password' => true]);

        $this->actingAs($user)->post('/password/change', [
            'password' => 'MoiSobstvennyi-2026',
            'password_confirmation' => 'MoiSobstvennyi-2026',
        ])->assertRedirect('/cabinet');

        $user->refresh();

        $this->assertFalse($user->must_change_password);
        $this->assertTrue(Hash::check('MoiSobstvennyi-2026', $user->password));
    }

    /**
     * Смена на тот же пароль формальна: доступ по-прежнему знают двое.
     */
    #[Test]
    public function прежний_пароль_не_принимается(): void
    {
        $user = User::factory()->create([
            'must_change_password' => true,
            'password' => 'VydannyiParol-2026',
        ]);

        $this->actingAs($user)->post('/password/change', [
            'password' => 'VydannyiParol-2026',
            'password_confirmation' => 'VydannyiParol-2026',
        ])->assertSessionHasErrors('password');

        $this->assertTrue($user->fresh()->must_change_password);
    }

    #[Test]
    public function несовпадающие_пароли_отклоняются(): void
    {
        $user = User::factory()->create(['must_change_password' => true]);

        $this->actingAs($user)->post('/password/change', [
            'password' => 'PervyiParol-2026',
            'password_confirmation' => 'VtoroiParol-2026',
        ])->assertSessionHasErrors(['password' => 'Пароли не совпадают']);
    }

    #[Test]
    public function гость_не_имеет_доступа(): void
    {
        $this->get('/password/change')->assertRedirect('/login');
    }
}
