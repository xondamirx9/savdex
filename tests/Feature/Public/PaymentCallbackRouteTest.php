<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Маршрут колбэков платёжных провайдеров.
 *
 * Merchant API Uzum — диалог из пяти операций (check, create, confirm,
 * reverse, status), которые провайдер вызывает на подпутях одной базы
 * /payments/uzum/callback. Провайдеру при подключении сообщается база —
 * поэтому все подпути обязаны существовать и быть свободными от CSRF:
 * провайдер о нашем токене не знает.
 *
 * Выключенный провайдер везде отвечает 404: до реализации протокола
 * эндпойнт ведёт себя так, будто его нет.
 */
class PaymentCallbackRouteTest extends TestCase
{
    use RefreshDatabase;

    /** @return array<string, array{string}> */
    public static function операции(): array
    {
        return [
            'база без операции' => [''],
            'check' => ['/check'],
            'create' => ['/create'],
            'confirm' => ['/confirm'],
            'reverse' => ['/reverse'],
            'status' => ['/status'],
        ];
    }

    /**
     * 404, а не 419: запрос без CSRF-токена дошёл до контроллера,
     * и уже тот ответил «выключенного провайдера не существует».
     */
    #[Test]
    #[DataProvider('операции')]
    public function подпуть_существует_и_свободен_от_csrf(string $operation): void
    {
        $this->postJson("/payments/uzum/callback{$operation}", ['x' => 1])
            ->assertNotFound();
    }

    /** GET запрещён на всей базе: колбэки приходят только POST. */
    #[Test]
    public function get_не_принимается(): void
    {
        $this->get('/payments/uzum/callback/check')->assertStatus(405);
    }
}
