<?php

declare(strict_types=1);

namespace Tests\Feature;

use App\Models\Setting;
use App\Support\Appearance;
use Database\Seeders\SettingSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Настройки, появившиеся после прошлого релиза, доезжают до прода.
 *
 * Раньше новая настройка заводилась только миграцией. Миграция
 * выполняется один раз и молча: если в тот деплой что-то пошло не так,
 * строки нет, кнопки в админке нет, и починить это без консоли нельзя —
 * а консоли на хостинге может не быть. Сидер выполняется на каждом
 * деплое и заводит недостающее.
 *
 * Обратная опасность — вернуть настройке значение из кода. Настройки
 * для того и существуют, чтобы их правил заказчик: деплой, стирающий
 * телефон поддержки или загруженный фон, — потеря данных.
 */
class SettingSeederTest extends TestCase
{
    use RefreshDatabase;

    #[Test]
    public function недостающая_настройка_заводится(): void
    {
        Setting::query()->where('key', Appearance::KEY_LOGO)->delete();
        Setting::flushCache();

        $this->seed(SettingSeeder::class);

        $setting = Setting::query()->where('key', Appearance::KEY_LOGO)->first();

        $this->assertNotNull($setting);
        $this->assertSame('appearance', $setting->group);
        $this->assertSame('image', $setting->type);
    }

    #[Test]
    public function заполненное_значение_не_перезаписывается(): void
    {
        // Первый прогон заводит строки, второй обязан их не трогать:
        // именно так это и выглядит на деплое
        $this->seed(SettingSeeder::class);

        Setting::put('support_phone', '+998 90 111-22-33');
        Setting::put(Appearance::KEY_HERO, 'appearance/fon.jpg');

        $this->seed(SettingSeeder::class);
        Setting::flushCache();

        $this->assertSame('+998 90 111-22-33', Setting::get('support_phone'));
        $this->assertSame('appearance/fon.jpg', Setting::get(Appearance::KEY_HERO));
    }

    /** Сидер идёт на каждом деплое: дубли ключей сломали бы Setting::values(). */
    #[Test]
    public function повторный_запуск_не_плодит_дублей(): void
    {
        $this->seed(SettingSeeder::class);

        $after = Setting::query()->count();

        $this->seed(SettingSeeder::class);

        $this->assertSame($after, Setting::query()->count());
        $this->assertSame(
            $after,
            Setting::query()->distinct()->count('key'),
            'Ключи настроек обязаны быть уникальными',
        );
    }

    /** Название и пояснение правят в админке — сидер их не откатывает. */
    #[Test]
    public function правки_названий_переживают_деплой(): void
    {
        Setting::query()->where('key', Appearance::KEY_LOGO)->update(['label' => 'Знак компании']);

        $this->seed(SettingSeeder::class);

        $this->assertSame(
            'Знак компании',
            Setting::query()->where('key', Appearance::KEY_LOGO)->value('label'),
        );
    }
}
