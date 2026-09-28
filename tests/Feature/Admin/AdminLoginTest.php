<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Pages\Auth\Login;
use App\Models\User;
use Filament\Facades\Filament;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Вход в админку: почта без учёта регистра, как на сайте.
 *
 * На PostgreSQL сравнение строк регистр различает, и стандартная форма
 * Filament не пускала «Boss@Savdex.uz» — телефон сам ставит заглавную
 * первую букву, — хотя на сайт с тем же вводом пускало.
 */
class AdminLoginTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();

        Filament::setCurrentPanel(Filament::getPanel('admin'));

        User::factory()->create([
            'email' => 'boss@savdex.uz',
            'password' => 'secret-password',
            'is_admin' => true,
            'admin_role' => User::ADMIN_SUPERADMIN,
            'status' => 'active',
        ]);
    }

    /** @return array<string, array{string}> */
    public static function написания(): array
    {
        return [
            'как хранится' => ['boss@savdex.uz'],
            'заглавная первая' => ['Boss@savdex.uz'],
            'заглавными (Caps Lock)' => ['BOSS@SAVDEX.UZ'],
        ];
    }

    #[Test]
    #[DataProvider('написания')]
    public function почта_без_учёта_регистра(string $email): void
    {
        Livewire::test(Login::class)
            ->fillForm(['email' => $email, 'password' => 'secret-password'])
            ->call('authenticate')
            ->assertHasNoFormErrors();

        $this->assertAuthenticated();
    }

    #[Test]
    public function неверный_пароль_не_пускает(): void
    {
        Livewire::test(Login::class)
            ->fillForm(['email' => 'Boss@savdex.uz', 'password' => 'wrong-password'])
            ->call('authenticate')
            ->assertHasFormErrors(['email']);

        $this->assertGuest();
    }

    #[Test]
    public function не_администратора_не_пускает(): void
    {
        User::factory()->create([
            'email' => 'buyer@savdex.uz',
            'password' => 'secret-password',
            'is_admin' => false,
        ]);

        Livewire::test(Login::class)
            ->fillForm(['email' => 'Buyer@savdex.uz', 'password' => 'secret-password'])
            ->call('authenticate')
            ->assertHasFormErrors(['email']);

        $this->assertGuest();
    }

    #[Test]
    public function форма_входа_открывается(): void
    {
        $this->get('/admin/login')->assertOk()->assertSeeLivewire(Login::class);
    }
}
