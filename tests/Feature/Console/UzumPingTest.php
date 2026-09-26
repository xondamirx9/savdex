<?php

declare(strict_types=1);

namespace Tests\Feature\Console;

use App\Console\Commands\UzumPing;
use PHPUnit\Framework\Attributes\Test;
use ReflectionMethod;
use Tests\TestCase;

/**
 * Прозвон Uzum: секреты в выводе.
 *
 * Вывод команды вставляют в задачу и пересылают в переписке — там
 * не должно быть ни ключа, ни пароля целиком. Так уже было с APP_KEY
 * в сентябре: ключ попал в скриншот и перестал быть секретом.
 */
class UzumPingTest extends TestCase
{
    private function mask(string $method, string $value): string
    {
        $reflection = new ReflectionMethod(UzumPing::class, $method);

        return (string) $reflection->invoke(null, $value);
    }

    #[Test]
    public function пароль_прокси_закрывается_целиком(): void
    {
        /*
         * Пароль с «@» внутри. Прежнее выражение обрывалось на первом
         * «@» и выпускало хвост: http://user:***@ss:word@host.
         */
        $закрыто = $this->mask('maskProxy', 'http://user:p@ss:word@proxy.host:3128');

        $this->assertSame('http://user:***@proxy.host:3128', $закрыто);
        $this->assertStringNotContainsString('ss:word', $закрыто);
    }

    #[Test]
    public function обычный_пароль_прокси_закрыт(): void
    {
        $this->assertSame(
            'http://user:***@proxy.example.com:8080',
            $this->mask('maskProxy', 'http://user:secret@proxy.example.com:8080'),
        );
    }

    #[Test]
    public function адрес_без_пароля_не_трогается(): void
    {
        $this->assertSame(
            'http://proxy.example.com:8080',
            $this->mask('maskProxy', 'http://proxy.example.com:8080'),
        );
        $this->assertSame(
            'http://noauth@proxy:8080',
            $this->mask('maskProxy', 'http://noauth@proxy:8080'),
        );
    }

    #[Test]
    public function пустой_прокси_объясняется_словами(): void
    {
        $this->assertSame('(пусто — прямое соединение)', $this->mask('maskProxy', ''));
    }

    #[Test]
    public function путь_после_порта_не_ломает_маскировку(): void
    {
        $this->assertSame(
            'http://user:***@proxy:8080/path',
            $this->mask('maskProxy', 'http://user:secret@proxy:8080/path'),
        );
    }

    #[Test]
    public function короткий_ключ_закрывается_целиком(): void
    {
        /* У шестизначного «первые три и последние три» не скрывает ничего. */
        $this->assertSame('******', $this->mask('mask', 'abcdef'));
    }

    #[Test]
    public function длинный_ключ_виден_только_краями(): void
    {
        $закрыто = $this->mask('mask', 'sk_live_0123456789abcdef');

        $this->assertStringNotContainsString('0123456789', $закрыто);
        $this->assertStringStartsWith('sk_', $закрыто);
        $this->assertStringEndsWith('def', $закрыто);
    }
}
