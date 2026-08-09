<?php

declare(strict_types=1);

namespace Tests\Feature\Auth;

use App\Services\Auth\LoginThrottle;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * NEG-02 и NEG-03 из QA.md — ограничение попыток входа.
 */
class LoginThrottleTest extends TestCase
{
    use RefreshDatabase;

    #[Test]
    public function новый_посетитель_имеет_полный_лимит_попыток(): void
    {
        $throttle = new LoginThrottle('rustam@company.uz', '10.0.0.1');

        $this->assertSame(LoginThrottle::MAX_ATTEMPTS, $throttle->remainingAttempts());
        $this->assertFalse($throttle->isLocked());
    }

    #[Test]
    public function каждая_неудача_уменьшает_остаток_попыток(): void
    {
        $throttle = new LoginThrottle('rustam@company.uz', '10.0.0.1');

        $throttle->recordFailure();
        $this->assertSame(4, (new LoginThrottle('rustam@company.uz', '10.0.0.1'))->remainingAttempts());

        $throttle->recordFailure();
        $this->assertSame(3, (new LoginThrottle('rustam@company.uz', '10.0.0.1'))->remainingAttempts());
    }

    #[Test]
    public function после_пятой_неудачи_вход_блокируется(): void
    {
        $throttle = new LoginThrottle('rustam@company.uz', '10.0.0.1');

        for ($i = 0; $i < LoginThrottle::MAX_ATTEMPTS; $i++) {
            $throttle->recordFailure();
        }

        $fresh = new LoginThrottle('rustam@company.uz', '10.0.0.1');

        $this->assertTrue($fresh->isLocked());
        $this->assertSame(0, $fresh->remainingAttempts());
        $this->assertGreaterThan(0, $fresh->secondsUntilUnlock());
    }

    #[Test]
    public function блокировка_привязана_к_связке_почта_и_ip(): void
    {
        // Иначе, зная чужой адрес, можно заблокировать чужой аккаунт
        $victim = new LoginThrottle('victim@company.uz', '10.0.0.1');

        for ($i = 0; $i < LoginThrottle::MAX_ATTEMPTS; $i++) {
            $victim->recordFailure();
        }

        $this->assertTrue((new LoginThrottle('victim@company.uz', '10.0.0.1'))->isLocked());

        // Та же почта с другого адреса не заблокирована
        $this->assertFalse((new LoginThrottle('victim@company.uz', '10.0.0.2'))->isLocked());
    }

    #[Test]
    public function успешный_вход_обнуляет_счётчик(): void
    {
        // Иначе блокировка догонит пользователя позже, уже после верного входа
        $throttle = new LoginThrottle('rustam@company.uz', '10.0.0.1');

        $throttle->recordFailure();
        $throttle->recordFailure();
        $throttle->recordFailure();

        $throttle->recordSuccess();

        $this->assertSame(
            LoginThrottle::MAX_ATTEMPTS,
            (new LoginThrottle('rustam@company.uz', '10.0.0.1'))->remainingAttempts(),
        );
    }

    #[Test]
    public function старые_попытки_выпадают_из_окна_подсчёта(): void
    {
        $throttle = new LoginThrottle('rustam@company.uz', '10.0.0.1');

        $this->travel(-20)->minutes();
        for ($i = 0; $i < LoginThrottle::MAX_ATTEMPTS; $i++) {
            $throttle->recordFailure();
        }
        $this->travelBack();

        $this->assertFalse(
            (new LoginThrottle('rustam@company.uz', '10.0.0.1'))->isLocked(),
            'Попытки старше 15 минут не должны учитываться',
        );
    }

    #[Test]
    public function пароль_и_адрес_попытки_не_сохраняются_в_открытом_виде(): void
    {
        $throttle = new LoginThrottle('rustam@company.uz', '10.0.0.1');
        $throttle->recordFailure('Mozilla/5.0 Test');

        $row = \DB::table('login_attempts')->first();

        $this->assertNotNull($row);
        $this->assertNotSame('Mozilla/5.0 Test', $row->user_agent_hash);
        $this->assertSame(64, strlen((string) $row->user_agent_hash), 'User-Agent должен храниться хешем');
    }
}
