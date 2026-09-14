<?php

declare(strict_types=1);

namespace Tests\Feature\Console;

use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\Config;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Проверка новой базы перед переносом данных.
 *
 * Здесь проверяется не подключение к PostgreSQL — его в тестах нет, —
 * а то, ради чего команда написана: она обязана отказать, когда
 * переносить данные нельзя, и сказать человеку, что именно чинить.
 */
class CheckPostgresTest extends TestCase
{
    private function check(): int
    {
        return Artisan::call('savdex:check-postgres');
    }

    #[Test]
    public function отказывает_когда_адрес_базы_не_задан(): void
    {
        Config::set('database.connections.pgsql_target.url', '');

        $this->assertSame(1, $this->check());

        $output = Artisan::output();

        $this->assertStringContainsString('TARGET_DB_URL', $output);
        $this->assertStringContainsString('Переносить данные пока нельзя', $output);
    }

    /**
     * Регион, тариф и список доступа из SQL не видны. Команда обязана
     * об этом сказать, иначе зелёный отчёт прочтут как «проверено всё».
     */
    #[Test]
    public function честно_перечисляет_непроверяемое(): void
    {
        Config::set('database.connections.pgsql_target.url', '');

        $this->check();

        $output = Artisan::output();

        $this->assertStringContainsString('Из SQL не видно', $output);
        $this->assertStringContainsString('регион', $output);
        $this->assertStringContainsString('тариф', $output);
    }

    /** Непонятная ошибка драйвера бесполезна тому, кто её увидит. */
    #[Test]
    public function объясняет_ошибку_подключения_по_человечески(): void
    {
        Config::set('database.connections.pgsql_target', [
            'driver' => 'pgsql',
            'url' => 'pgsql://someone:secret@no-such-host.invalid:5432/savdex',
            'charset' => 'utf8',
            'prefix' => '',
            'prefix_indexes' => true,
            'search_path' => 'public',
            'sslmode' => 'prefer',
        ]);

        $this->assertSame(1, $this->check());

        $output = Artisan::output();

        $this->assertStringContainsString('Соединение', $output);
        $this->assertStringContainsString('Переносить данные пока нельзя', $output);
    }
}
