<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Models\User;
use App\Support\AdminAccess;
use App\Support\PythonBridge;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Переход из админки в разделы на Django (этап 2 переноса).
 *
 * Laravel выдаёт пропуск только вошедшему сотруднику; сам пропуск —
 * подписанный номер, адрес и срок. Принимает и проверяет его Django
 * (python/savdex/bridge.py), совпадение подписи двух половин сверяет
 * python/tests/test_bridge_parity.py.
 */
class PythonBridgeTest extends TestCase
{
    use RefreshDatabase;

    private function admin(array $attributes = []): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => AdminAccess::CONTENT_MANAGER,
            'status' => 'active',
            ...$attributes,
        ]);
    }

    /** Разобрать пропуск так, как это делает Django. */
    private function decode(string $token): array
    {
        [$payload, $signature] = explode('.', $token);
        $raw = fn (string $s): string => base64_decode(strtr($s, '-_', '+/'));

        $this->assertTrue(hash_equals(hash_hmac('sha256', $payload, PythonBridge::key(), true), $raw($signature)), 'подпись');

        return json_decode($raw($payload), true);
    }

    private function tokenFrom(string $html): string
    {
        $this->assertSame(1, preg_match('/name="token" value="([^"]+)"/', $html, $m));

        return html_entity_decode($m[1]);
    }

    #[Test]
    public function сотрудник_получает_пропуск_в_форме(): void
    {
        $admin = $this->admin();

        // Адрес — закодированным: помощник get() в тестах срезает
        // конечную косую черту со всей строки, вместе с запросом
        $response = $this->actingAs($admin)->get('/admin/python?'.http_build_query(['next' => '/py/admin/geo/']));

        $response->assertOk()
            ->assertHeader('Cache-Control', 'no-store, private')
            ->assertHeader('Referrer-Policy', 'no-referrer')
            ->assertSee('action="/py/login"', false)
            ->assertSee('method="post"', false);

        $data = $this->decode($this->tokenFrom($response->getContent()));

        $this->assertSame($admin->id, $data['uid']);
        $this->assertSame('/py/admin/geo/', $data['next']);
        $this->assertEqualsWithDelta(time() + PythonBridge::TTL, $data['exp'], 5);
    }

    #[Test]
    public function без_входа_пропуска_нет(): void
    {
        $this->get('/admin/python')->assertRedirect();
    }

    #[Test]
    public function не_сотруднику_пропуска_нет(): void
    {
        $this->actingAs(User::factory()->create(['is_admin' => false]))
            ->get('/admin/python')
            ->assertForbidden();
    }

    #[Test]
    public function заблокированному_пропуска_нет(): void
    {
        $this->actingAs($this->admin(['status' => 'blocked']))
            ->get('/admin/python')
            ->assertForbidden();
    }

    /** Выданный пароль ещё не сменён — сначала смена пароля, как в остальной админке. */
    #[Test]
    public function до_смены_пароля_пропуска_нет(): void
    {
        $this->actingAs($this->admin(['must_change_password' => true]))
            ->get('/admin/python')
            ->assertRedirect(route('password.forced'));
    }

    /** Адрес из запроса — только в Django-админку, иначе пропуск стал бы переадресацией куда угодно. */
    #[Test]
    public function чужой_адрес_заменяется_на_главную_django_админки(): void
    {
        foreach (['https://evil.example/', '//evil.example/py/admin/', '/py/admin//evil', '/py/admin/\\x', '/admin', '', "/py/admin/\n"] as $next) {
            $this->assertSame(PythonBridge::HOME, PythonBridge::safeNext($next), $next);
        }

        $this->assertSame('/py/admin/geo/countries?page=2', PythonBridge::safeNext('/py/admin/geo/countries?page=2'));
    }

    /** Пока в разделах на Python только проверка входа — пункт меню видит суперадмин. */
    #[Test]
    public function пункт_меню_только_суперадмину(): void
    {
        $this->actingAs($this->admin(['admin_role' => AdminAccess::SUPERADMIN]))
            ->get('/admin')
            ->assertOk()
            ->assertSee('Админка на Python');

        $this->actingAs($this->admin(['admin_role' => AdminAccess::ADMIN]))
            ->get('/admin')
            ->assertOk()
            ->assertDontSee('Админка на Python');
    }

    /** Ключ подписи выведен из APP_KEY, но им не является. */
    #[Test]
    public function ключ_подписи_не_app_key(): void
    {
        $appKey = base64_decode(substr((string) config('app.key'), 7));

        $this->assertSame(32, strlen(PythonBridge::key()));
        $this->assertNotSame($appKey, PythonBridge::key());
    }
}
