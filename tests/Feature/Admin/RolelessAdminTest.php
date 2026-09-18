<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Models\User;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Администратор, которому ещё не назначили роль.
 *
 * Между «человека завели» и «человеку выдали роль» проходит время —
 * иногда дни. Всё это время он уже может войти в панель, и до выдачи
 * роли не должен видеть ни строки чужих данных.
 *
 * Пустое меню защитой не считается: проверяется заход по прямому
 * адресу, потому что адрес раздела угадывается с первого раза.
 */
class RolelessAdminTest extends TestCase
{
    use RefreshDatabase;

    private function roleless(): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => null,
            'status' => 'active',
        ]);
    }

    /** @return list<string> адреса разделов панели */
    public static function адресаРазделов(): array
    {
        return [
            'компании' => ['/admin/companies'],
            'объявления' => ['/admin/listings'],
            'пользователи' => ['/admin/users'],
            'счета' => ['/admin/invoices'],
            'возвраты' => ['/admin/refunds'],
            'финансовые операции' => ['/admin/finance-operations'],
            'финансовые отчёты' => ['/admin/finance-reports'],
            'сверка со шлюзом' => ['/admin/gateway-reconciliation'],
            'журнал действий' => ['/admin/admin-actions'],
            'роли и права' => ['/admin/roles'],
            'лиды' => ['/admin/crm/leads'],
            'обращения' => ['/admin/tickets'],
            'страны' => ['/admin/countries'],
            'настройки' => ['/admin/settings'],
        ];
    }

    #[DataProvider('адресаРазделов')]
    #[Test]
    public function без_роли_разделы_закрыты_и_по_прямому_адресу(string $url): void
    {
        $response = $this->actingAs($this->roleless())->get($url);

        $this->assertContains(
            $response->getStatusCode(),
            [403, 404],
            "{$url} обязан быть закрыт для администратора без роли, а вернул {$response->getStatusCode()}",
        );
    }

    /** Войти он может — иначе не поймёт, что ждёт выдачи роли. */
    #[Test]
    public function в_панель_пускает(): void
    {
        $this->actingAs($this->roleless())->get('/admin')->assertOk();
    }

    /** Но данных площадки на инфопанели нет. */
    #[Test]
    public function на_инфопанели_нет_данных_площадки(): void
    {
        $response = $this->actingAs($this->roleless())->get('/admin');

        foreach (['Выручка', 'Компаний', 'Объявлений', 'Воронка'] as $forbidden) {
            $response->assertDontSee($forbidden, escape: false);
        }
    }

    /** Пустой экран без слов читается как поломка — объяснение обязано быть. */
    #[Test]
    public function на_инфопанели_объясняется_почему_пусто(): void
    {
        $this->actingAs($this->roleless())
            ->get('/admin')
            ->assertOk()
            ->assertSee('Роль ещё не назначена')
            ->assertSee('это не сбой');
    }

    /** Тому, у кого роль есть, объяснение не нужно и мешало бы. */
    #[Test]
    public function с_ролью_объяснение_не_показывается(): void
    {
        $finance = User::factory()->create([
            'is_admin' => true,
            'admin_role' => AdminAccess::FINANCE,
            'status' => 'active',
        ]);

        $this->actingAs($finance)
            ->get('/admin')
            ->assertOk()
            ->assertDontSee('Роль ещё не назначена');
    }

    /**
     * Роль есть, но все права сняты персонально — человек видит ту же
     * пустоту и не должен остаться без объяснения.
     */
    #[Test]
    public function объяснение_показывается_и_когда_права_сняты_поимённо(): void
    {
        $stripped = User::factory()->create([
            'is_admin' => true,
            'admin_role' => AdminAccess::CONTENT_MANAGER,
            'status' => 'active',
        ]);

        $stripped->forceFill([
            'admin_permissions' => ['revoke' => $stripped->adminAbilities()],
        ])->save();

        $this->actingAs($stripped->fresh())
            ->get('/admin')
            ->assertOk()
            ->assertSee('Роль ещё не назначена');
    }
}
