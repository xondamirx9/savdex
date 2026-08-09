<?php

declare(strict_types=1);

namespace Tests\Feature;

use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Ни один экран, доступный пользователю, не должен остаться заглушкой.
 *
 * Появился после ручного прохода регистрации: маршруты, контроллеры
 * и тесты для подтверждения почты и сброса пароля были написаны,
 * а сами страницы остались текстом «Экран реализуется в оставшейся
 * части спринта 1». Тесты проверяли коды ответов и редиректы и потому
 * молчали — человек же упирался в пустой экран сразу после регистрации.
 *
 * Проверка идёт по исходникам, а не по HTTP: заглушка отдаёт честные 200.
 */
class ScreensImplementedTest extends TestCase
{
    /**
     * Экраны, до которых пользователь доходит в обычном сценарии.
     * Раздел кабинета cabinet/Soon сюда не входит: он сообщает
     * о нереализованном разделе намеренно и по делу.
     */
    private const SCREENS = [
        'auth/Login',
        'auth/Register',
        'auth/VerifyEmail',
        'auth/ForgotPassword',
        'auth/ResetPassword',
        'auth/ForcePassword',
        'cabinet/Dashboard',
    ];

    #[Test]
    public function экраны_не_заглушки(): void
    {
        $stubs = [];

        foreach (self::SCREENS as $screen) {
            $path = resource_path("js/pages/{$screen}.tsx");

            $this->assertFileExists($path, "Нет файла экрана {$screen}");

            $code = (string) file_get_contents($path);

            if (str_contains($code, 'Экран реализуется') || str_contains($code, 'в разработке')) {
                $stubs[] = $screen;
            }
        }

        $this->assertSame([], $stubs, 'Эти экраны — заглушки, но пользователь на них попадает');
    }
}
