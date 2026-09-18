<?php

declare(strict_types=1);

namespace Tests\Unit;

use App\Support\Runtime;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use PHPUnit\Framework\TestCase;

/**
 * Где работает приложение — у разработчика или у людей.
 *
 * Правило выглядит мелочью, но именно оно решало, падает ли страница
 * у живого посетителя: площадка с APP_ENV=staging получала полный
 * набор предохранителей разработки.
 */
class RuntimeTest extends TestCase
{
    /** @return array<string, array{string}> */
    public static function окруженияРазработчика(): array
    {
        return [
            'местное' => ['local'],
            'тесты' => ['testing'],
        ];
    }

    /**
     * @return array<string, array{?string}>
     */
    public static function развёрнутыеОкружения(): array
    {
        return [
            'боевое' => ['production'],
            // То самое значение, из-за которого всё и началось
            'промежуточное' => ['staging'],
            'демо-стенд' => ['demo'],
            'опечатка' => ['prodcution'],
            'пусто' => [''],
            'не задано' => [null],
        ];
    }

    #[Test]
    #[DataProvider('окруженияРазработчика')]
    public function машина_разработчика_распознаётся(string $environment): void
    {
        $this->assertTrue(Runtime::isDeveloperMachine($environment));
        $this->assertFalse(Runtime::isDeployed($environment));
    }

    /**
     * Незнакомое окружение считается боевым.
     *
     * Цена ошибки несимметрична: лишняя осторожность у разработчика
     * стоит неудобства, недостаточная на живом сайте — упавшей
     * страницы у посетителя.
     */
    #[Test]
    #[DataProvider('развёрнутыеОкружения')]
    public function всё_остальное_считается_развёрнутым(?string $environment): void
    {
        $this->assertTrue(Runtime::isDeployed($environment));
        $this->assertFalse(Runtime::isDeveloperMachine($environment));
    }

    /** Одно из двух, и никогда оба сразу. */
    #[Test]
    public function два_состояния_исключают_друг_друга(): void
    {
        foreach (['local', 'testing', 'production', 'staging', 'что угодно', null] as $environment) {
            $this->assertNotSame(
                Runtime::isDeveloperMachine($environment),
                Runtime::isDeployed($environment),
                var_export($environment, true),
            );
        }
    }
}
