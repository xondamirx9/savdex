<?php

declare(strict_types=1);

namespace Tests\Feature;

use Illuminate\Support\Facades\Route;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Целостность маршрутов.
 *
 * Появился после дефекта «Route [verification.verify] not defined»:
 * отсутствующий маршрут ронял регистрацию с 500, причём уже после
 * создания пользователя. Ошибку невозможно поймать компилятором —
 * route() принимает любую строку и падает только в момент вызова.
 *
 * Этот тест проверяет, что все маршруты, на которые ссылается код
 * приложения и стандартные уведомления Laravel, действительно есть.
 */
class RoutesIntegrityTest extends TestCase
{
    /**
     * Маршруты, которые обязаны существовать, потому что на них
     * ссылается не наш код, а фреймворк и его уведомления.
     *
     * @return list<array{string, string}>
     */
    public static function обязательныеМаршруты(): array
    {
        return [
            ['login', 'редирект неавторизованного пользователя'],
            ['register', 'ссылки в интерфейсе'],
            ['password.request', 'ссылка «Забыли пароль»'],
            ['password.email', 'отправка письма для сброса'],
            ['password.reset', 'ссылка внутри письма ResetPassword'],
            ['password.update', 'сохранение нового пароля'],
            ['verification.notice', 'редирект middleware verified'],
            ['verification.verify', 'ссылка внутри письма VerifyEmail'],
            ['verification.send', 'кнопка «Отправить повторно»'],
            ['logout', 'выход'],
            ['cabinet', 'редирект после входа'],
            ['home', 'редирект после выхода'],
        ];
    }

    #[Test]
    #[DataProvider('обязательныеМаршруты')]
    public function маршрут_существует(string $name, string $why): void
    {
        $this->assertTrue(
            Route::has($name),
            "Маршрут [{$name}] не определён, хотя нужен: {$why}",
        );
    }

    /**
     * Все имена маршрутов, встречающиеся в вызовах route() внутри
     * приложения, должны быть зарегистрированы.
     */
    #[Test]
    public function все_вызовы_route_ссылаются_на_существующие_маршруты(): void
    {
        $missing = [];

        foreach ($this->phpFiles(app_path()) as $file) {
            $code = file_get_contents($file) ?: '';

            preg_match_all("/(?:route|redirect\(\)->route)\(\s*'([a-z0-9_.-]+)'/i", $code, $matches);

            foreach ($matches[1] as $name) {
                if (! Route::has($name)) {
                    $missing[] = $name.' — '.str_replace(base_path().DIRECTORY_SEPARATOR, '', $file);
                }
            }
        }

        $this->assertSame(
            [],
            array_values(array_unique($missing)),
            'Код ссылается на несуществующие маршруты',
        );
    }

    /** @return list<string> */
    private function phpFiles(string $dir): array
    {
        $files = [];
        $it = new \RecursiveIteratorIterator(new \RecursiveDirectoryIterator($dir));

        foreach ($it as $file) {
            if ($file->isFile() && $file->getExtension() === 'php') {
                $files[] = $file->getPathname();
            }
        }

        return $files;
    }
}
