<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Русский перевод админки.
 *
 * Русская локаль Filament отстаёт от английской: над списком компаний
 * висело «filament-tables::table.result_count» — служебный ключ там,
 * где должно быть «14 записей». Недостающие строки лежат в
 * lang/vendor/*; тест сравнивает их с английским оригиналом, чтобы
 * обновление пакета не вернуло ключи на экран.
 *
 * Файлы читаются с диска, а не через Lang::has: пространства имён
 * Filament регистрируются при загрузке панели, и в тесте без запроса
 * к /admin проверка сказала бы «не переведено» про строки, которые
 * на самом деле переводятся.
 */
class AdminTranslationsTest extends TestCase
{
    /**
     * Пакеты Filament, чьи строки видит администратор:
     * пространство имён => путь в vendor.
     */
    private const PACKAGES = [
        'filament' => 'filament/filament',
        'filament-forms' => 'filament/forms',
        'filament-infolists' => 'filament/infolists',
        'filament-notifications' => 'filament/notifications',
        'filament-query-builder' => 'filament/query-builder',
        'filament-schemas' => 'filament/schemas',
        'filament-tables' => 'filament/tables',
        'filament-widgets' => 'filament/widgets',
    ];

    /** @return array<string, string> */
    private function flatten(array $items, string $prefix = ''): array
    {
        $flat = [];

        foreach ($items as $key => $value) {
            $path = $prefix === '' ? (string) $key : "{$prefix}.{$key}";

            if (is_array($value)) {
                $flat += $this->flatten($value, $path);

                continue;
            }

            $flat[$path] = (string) $value;
        }

        return $flat;
    }

    /** @return array<string, string> */
    private function keysOf(string $file): array
    {
        return is_file($file) ? $this->flatten(require $file) : [];
    }

    #[Test]
    public function в_админке_не_осталось_непереведённых_строк(): void
    {
        $untranslated = [];

        foreach (self::PACKAGES as $namespace => $path) {
            foreach (glob(base_path("vendor/{$path}/resources/lang/en/*.php")) as $english) {
                $group = basename($english, '.php');

                $translated = $this->keysOf(str_replace('/lang/en/', '/lang/ru/', $english))
                    // Накладка накрывает то, чего нет в переводе пакета
                    + $this->keysOf(lang_path("vendor/{$namespace}/ru/{$group}.php"));

                foreach (array_keys($this->keysOf($english)) as $key) {
                    if (! array_key_exists($key, $translated)) {
                        $untranslated[] = "{$namespace}::{$group}.{$key}";
                    }
                }
            }
        }

        $this->assertSame(
            [],
            $untranslated,
            'Эти строки покажутся администратору как служебные ключи. Добавьте их в lang/vendor/<пакет>/ru/',
        );
    }

    /** Накладка дополняет перевод пакета, а не заменяет его целиком. */
    #[Test]
    public function накладка_не_затирает_готовый_перевод(): void
    {
        $this->app->setLocale('ru');

        $this->assertSame('Фильтр', __('filament-tables::table.actions.filter.label'));
        $this->assertSame('3 записи', trans_choice('filament-tables::table.result_count', 3, ['count' => 3]));
    }
}
