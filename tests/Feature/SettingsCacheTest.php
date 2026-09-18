<?php

declare(strict_types=1);

namespace Tests\Feature;

use App\Models\Setting;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Cache;
use Illuminate\Support\Facades\DB;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

class SettingsCacheTest extends TestCase
{
    use RefreshDatabase;

    private function setting(string $key, string $value): Setting
    {
        return Setting::query()->create([
            'group' => 'contacts',
            'key' => $key,
            'label' => $key,
            'type' => 'string',
            'value' => $value,
        ]);
    }

    /**
     * Кэш в базе — как на боевой площадке. В тестах он по умолчанию
     * «array» и до базы не доходит вовсе, поэтому счётчик запросов
     * показывал бы ноль и с правкой, и без неё: тест зеленел бы,
     * ничего не проверяя.
     */
    private function useDatabaseCache(): void
    {
        config(['cache.default' => 'database']);

        foreach (['cache', 'cache.store', 'cache.__memoized:database'] as $binding) {
            $this->app->forgetInstance($binding);
        }

        Cache::clearResolvedInstances();
    }

    /**
     * Память запроса, начатая заново, — так каждый посетитель и
     * приходит: хранилище прогрето, память процесса пуста.
     */
    private function newRequestMemory(): void
    {
        $this->app->forgetInstance('cache.__memoized:database');
    }

    /**
     * Общие свойства Inertia читают шесть настроек на каждую страницу.
     * Пока кэш лежал в базе, это были шесть запросов за одним и тем же
     * ключом — ради данных, которые меняются раз в месяц.
     */
    #[Test]
    public function шесть_чтений_подряд_стоят_одного_обращения_к_хранилищу(): void
    {
        $this->useDatabaseCache();
        $this->setting('support_phone', '+998 71 000-00-00');

        // Прогрев хранилища: измеряем установившийся режим, а не промах.
        Setting::flushCache();
        Setting::values();
        $this->newRequestMemory();

        $reads = 0;
        DB::listen(function ($query) use (&$reads): void {
            if (str_contains($query->sql, '"cache"') || str_contains($query->sql, '`cache`')) {
                $reads++;
            }
        });

        foreach (['support_email', 'support_phone', 'support_hours', 'telegram', 'legal_name', 'legal_tin'] as $key) {
            Setting::get($key);
        }

        $this->assertSame(1, $reads, 'шесть чтений обязаны стоить одного обращения к хранилищу, остальные — из памяти запроса');
    }

    /** Значение обязано быть верным, а не только дешёвым. */
    #[Test]
    public function читается_то_что_записано(): void
    {
        $this->setting('support_phone', '+998 71 000-00-00');

        $this->assertSame('+998 71 000-00-00', Setting::get('support_phone'));
        $this->assertSame('запасное', Setting::get('нет_такой_настройки', 'запасное'));
    }

    /**
     * Память запроса опаснее кэша: страница, сохранившая настройку,
     * может дочитать старое значение и показать его — это и выглядит
     * как «не сохранилось».
     */
    #[Test]
    public function правка_видна_в_том_же_запросе(): void
    {
        $row = $this->setting('support_phone', 'старый');

        $this->assertSame('старый', Setting::get('support_phone'));

        $row->update(['value' => 'новый']);

        $this->assertSame('новый', Setting::get('support_phone'), 'сохранение обязано сбрасывать и память запроса');
    }

    /** put() правит строку в обход модели — события не срабатывают, сброс нужен явный. */
    #[Test]
    public function put_тоже_сбрасывает_память(): void
    {
        $this->setting('support_phone', 'старый');

        $this->assertSame('старый', Setting::get('support_phone'));

        Setting::put('support_phone', 'новый');

        $this->assertSame('новый', Setting::get('support_phone'));
    }

    /** Строки правят и миграциями, через DB::table — на это есть flushCache(). */
    #[Test]
    public function явный_сброс_подхватывает_правку_в_обход_модели(): void
    {
        $this->setting('support_phone', 'старый');
        $this->assertSame('старый', Setting::get('support_phone'));

        DB::table('settings')->where('key', 'support_phone')->update(['value' => json_encode('новый')]);
        Setting::flushCache();

        $this->assertSame('новый', Setting::get('support_phone'));
    }
}
