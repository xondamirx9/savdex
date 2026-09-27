<?php

declare(strict_types=1);

namespace Tests\Feature\Console;

use App\Console\Commands\ExportUiForPython;
use App\Support\Locales;
use Illuminate\Support\Facades\File;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Словарь и подписи «назад» для страниц на Django (этап 3 переноса):
 * Django должен говорить теми же словами, что Laravel.
 */
class ExportUiForPythonTest extends TestCase
{
    #[Test]
    public function выгружает_словарь_и_подписи_на_всех_языках(): void
    {
        $this->artisan('savdex:export-ui')->assertSuccessful();

        foreach (Locales::codes() as $locale) {
            $data = json_decode(File::get(ExportUiForPython::directory()."/{$locale}.json"), true);

            $this->assertIsArray($data['translations']);
            $this->assertArrayHasKey('nav', $data['translations']);
            $this->assertCount(59, $data['ago']['minute']);
        }

        $ru = json_decode(File::get(ExportUiForPython::directory().'/ru.json'), true);
        $this->assertSame('5 минут назад', $ru['ago']['minute'][5]);
        $this->assertSame('2 недели назад', $ru['ago']['week'][2]);
        // Словарь — как проп translations у Laravel
        $this->assertSame(trans('ui.nav.help', locale: 'ru'), $ru['translations']['nav']['help']);
    }

    #[Test]
    public function незаполненный_ключ_языка_берётся_из_русского(): void
    {
        app('translator')->addLines(['ui.probe.only_russian' => 'Только по-русски'], 'ru');

        $this->artisan('savdex:export-ui')->assertSuccessful();

        $en = json_decode(File::get(ExportUiForPython::directory().'/en.json'), true);
        $this->assertSame('Только по-русски', $en['translations']['probe']['only_russian']);
    }
}
