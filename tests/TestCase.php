<?php

namespace Tests;

use App\Http\Controllers\Auth\RegisteredUserController;
use Illuminate\Foundation\Testing\TestCase as BaseTestCase;
use Illuminate\Http\Response;
use Illuminate\Support\Facades\Http;
use Illuminate\Testing\TestResponse;

abstract class TestCase extends BaseTestCase
{
    protected function setUp(): void
    {
        parent::setUp();

        // Тест не ходит в интернет: курс ЦБ, переводчик и касса
        // подменяются Http::fake, а забытая подмена падает здесь,
        // а не ждёт таймаута чужого сервиса
        Http::preventStrayRequests();
    }

    /**
     * Третий шаг регистрации (анкета) с почтой, уже подтверждённой
     * кодом на первых двух: адрес из $data кладётся в сессию, как его
     * положил бы RegisteredUserController::confirmCode.
     *
     * @param  array<string, mixed>  $data
     * @return TestResponse<Response>
     */
    protected function postRegistration(array $data): TestResponse
    {
        $email = mb_strtolower(trim((string) ($data['email'] ?? '')));

        return $this->withSession([
            RegisteredUserController::SESSION_EMAIL => $email,
            RegisteredUserController::SESSION_VERIFIED => $email,
        ])->post('/register', $data);
    }
}
