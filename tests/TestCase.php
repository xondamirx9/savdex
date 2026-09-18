<?php

namespace Tests;

use Illuminate\Foundation\Testing\TestCase as BaseTestCase;
use Illuminate\Support\Facades\Http;

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
}
