<?php

declare(strict_types=1);

namespace Tests\Feature\Public;

use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Testing\TestResponse;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Переезд со служебного адреса Render на свой домен.
 *
 * Render продолжает отдавать сайт по своему адресу и после привязки
 * домена. Пока оба адреса живы, поисковик выбирает главный сам,
 * и выбор нередко падает на служебный.
 */
class CanonicalHostTest extends TestCase
{
    use RefreshDatabase;

    /** Запрос приходит на служебный адрес хостинга. */
    private function fromHosting(string $uri, string $method = 'GET'): TestResponse
    {
        return $this->call($method, 'http://savdex.onrender.com'.$uri);
    }

    #[Test]
    public function запрос_со_служебного_адреса_уводится_на_домен(): void
    {
        config(['app.url' => 'https://savdex.uz']);

        $this->fromHosting('/about')
            ->assertStatus(301)
            ->assertRedirect('https://savdex.uz/about');
    }

    /**
     * 301, а не 302: постоянное перенаправление поисковик переносит
     * на новый адрес вместе с накопленным весом, временное — нет.
     */
    #[Test]
    public function перенаправление_постоянное(): void
    {
        config(['app.url' => 'https://savdex.uz']);

        $this->assertSame(301, $this->fromHosting('/')->getStatusCode());
    }

    /** Человек пришёл по ссылке на страницу — он должен на ней и оказаться. */
    #[Test]
    public function путь_язык_и_параметры_запроса_сохраняются(): void
    {
        config(['app.url' => 'https://savdex.uz']);

        $this->fromHosting('/uz/catalog?category=3&sort=cheap')
            ->assertRedirect('https://savdex.uz/uz/catalog?category=3&sort=cheap');
    }

    /**
     * Проверку живости Render дёргает по своему адресу и ждёт 200:
     * перенаправление он засчитает как «сервис не отвечает» и снимет
     * его с обслуживания.
     */
    #[Test]
    public function проверка_живости_отвечает_и_на_служебном_адресе(): void
    {
        config(['app.url' => 'https://savdex.uz']);

        $this->fromHosting('/up')->assertOk();
    }

    /**
     * На POST перенаправлять нельзя: по 301 клиент повторяет запрос
     * методом GET и без тела — колбэк платёжного провайдера, пришедший
     * на старый адрес, потерялся бы молча.
     */
    #[Test]
    public function небезопасные_методы_не_перенаправляются(): void
    {
        config(['app.url' => 'https://savdex.uz']);

        $this->assertNotSame(301, $this->fromHosting('/login', 'POST')->getStatusCode());
    }

    /** Свой домен — конечная точка, дальше уводить некуда. */
    #[Test]
    public function запрос_на_свой_домен_не_трогается(): void
    {
        config(['app.url' => 'https://savdex.uz']);

        $this->call('GET', 'https://savdex.uz/about')->assertOk();
    }

    /**
     * Пока домен не привязан, APP_URL — это адрес самого Render.
     * Перенаправление на себя же зациклило бы сайт целиком.
     */
    #[Test]
    public function без_своего_домена_перенаправления_нет(): void
    {
        config(['app.url' => 'https://savdex.onrender.com']);

        $this->fromHosting('/about')->assertOk();
    }

    /** Локальная разработка и тесты живут на других хостах — их не касается. */
    #[Test]
    public function локальный_адрес_не_трогается(): void
    {
        config(['app.url' => 'https://savdex.uz']);

        $this->call('GET', 'http://localhost/about')->assertOk();
    }
}
