<?php

declare(strict_types=1);

namespace Tests\Feature\Auth;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Hash;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Вход после регистрации с телефона.
 *
 * Человек зарегистрировался, вышел и не смог войти с тем же паролем:
 * при регистрации пароль набирали в показанном виде, и клавиатура
 * телефона сделала первую букву заглавной или дописала пробел. Такие
 * искажения вход теперь прощает, а почту ищет без учёта регистра.
 */
class LoginKeyboardTest extends TestCase
{
    use RefreshDatabase;

    private function user(string $storedPassword, string $email = 'rustam@company.uz'): User
    {
        return User::factory()->create([
            'email' => $email,
            'password' => $storedPassword,
            'status' => 'active',
        ]);
    }

    #[Test]
    public function клавиатура_сделала_первую_букву_заглавной(): void
    {
        $user = $this->user('Cement2026x');

        $this->post('/login', ['email' => 'rustam@company.uz', 'password' => 'cement2026x'])
            ->assertRedirect('/cabinet');

        $this->assertAuthenticatedAs($user);
        // Пароль пересохранён как набран сейчас — дальше вход напрямую
        $this->assertTrue(Hash::check('cement2026x', $user->fresh()->password));
    }

    #[Test]
    public function клавиатура_дописала_пробел_в_конце(): void
    {
        $user = $this->user('Cement2026x ');

        $this->post('/login', ['email' => 'rustam@company.uz', 'password' => 'cement2026x'])
            ->assertRedirect('/cabinet');

        $this->assertAuthenticatedAs($user);
    }

    #[Test]
    public function почта_с_заглавными_в_базе_находится(): void
    {
        $user = $this->user('Cement2026x');
        // Как учётка, заведённая до нормализации: мутатор модели обходим
        DB::table('users')->where('id', $user->id)->update(['email' => 'Rustam@Company.uz']);

        $this->post('/login', ['email' => 'rustam@company.uz', 'password' => 'Cement2026x'])
            ->assertRedirect('/cabinet');

        $this->assertAuthenticatedAs($user);
    }

    #[Test]
    public function действительно_неверный_пароль_не_проходит(): void
    {
        $this->user('Cement2026x');

        $this->post('/login', ['email' => 'rustam@company.uz', 'password' => 'Cement2027x'])
            ->assertSessionHasErrors('email');

        $this->assertGuest();
    }

    #[Test]
    public function почта_сохраняется_в_нижнем_регистре(): void
    {
        $user = $this->user('Cement2026x', ' Rustam@Company.UZ ');

        $this->assertSame('rustam@company.uz', $user->fresh()->email);
    }
}
