<?php

declare(strict_types=1);

namespace Tests\Feature;

use Illuminate\Support\Facades\File;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Словарь страниц Django (python/savdex/locale/ui) не отстал от lang/*.
 *
 * С шага 73 Django читает выгрузку из своего кода, а не из выгрузки при
 * старте службы. Поправили lang/<язык>/*.php и не выгрузили — страницы
 * Django заговорят старыми словами; этот тест такого не пропустит.
 */
class ExportUiForPythonTest extends TestCase
{
    #[Test]
    public function выгрузка_в_коде_python_свежая(): void
    {
        $fresh = 'storage/framework/testing/ui-'.getmypid();

        try {
            $this->artisan('savdex:export-ui', ['--to' => $fresh])->assertSuccessful();

            foreach (['ru', 'uz', 'en', 'zh', 'tr'] as $locale) {
                $this->assertFileEquals(
                    base_path("{$fresh}/{$locale}.json"),
                    base_path("python/savdex/locale/ui/{$locale}.json"),
                    "Словарь {$locale} устарел: php artisan savdex:export-ui --to=python/savdex/locale/ui",
                );
            }
        } finally {
            File::deleteDirectory(base_path($fresh));
        }
    }
}
