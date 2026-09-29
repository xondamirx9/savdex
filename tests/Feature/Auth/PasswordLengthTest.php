<?php

declare(strict_types=1);

namespace Tests\Feature\Auth;

use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\Support\LegalRegistration;
use Tests\TestCase;

/**
 * Пароль при регистрации — от 8 до 20 символов, и без согласия
 * с офертой регистрация не проходит.
 */
class PasswordLengthTest extends TestCase
{
    use LegalRegistration;
    use RefreshDatabase;

    /** @return array<string, mixed> */
    private function form(string $password, bool $terms = true): array
    {
        return [
            'name' => 'Алишер Каримов',
            'email' => 'alisher@mail.uz',
            'phone' => '+998 90 123-45-67',
            'password' => $password,
            'password_confirmation' => $password,
            'terms' => $terms,
            ...$this->legalFields(),
        ];
    }

    /** @return array<string, array{string}> */
    public static function допустимые(): array
    {
        return [
            'ровно 8' => ['Parol123'],
            'ровно 20' => ['Parol123Parol123Paro'],
        ];
    }

    #[Test]
    #[DataProvider('допустимые')]
    public function пароль_от_8_до_20_принимается(string $password): void
    {
        $this->postRegistration($this->form($password))->assertSessionHasNoErrors();

        $this->assertDatabaseHas('users', ['email' => 'alisher@mail.uz']);
    }

    #[Test]
    public function короче_8_отклоняется_с_понятным_сообщением(): void
    {
        $this->postRegistration($this->form('Parol12'))
            ->assertSessionHasErrors(['password' => __('ui.messages.register.password_min')]);
    }

    #[Test]
    public function длиннее_20_отклоняется_с_понятным_сообщением(): void
    {
        $this->postRegistration($this->form('Parol123Parol123Parol'))
            ->assertSessionHasErrors(['password' => __('ui.messages.register.password_max')]);

        $this->assertSame(0, User::query()->count());
    }

    #[Test]
    public function без_согласия_с_офертой_регистрации_нет(): void
    {
        $this->postRegistration($this->form('Parol123', terms: false))
            ->assertSessionHasErrors('terms');

        $this->assertSame(0, User::query()->count());
    }
}
