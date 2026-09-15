<?php

declare(strict_types=1);

use App\Models\Setting;
use App\Support\Appearance;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Логотип площадки — настройкой, а не файлом в репозитории.
 *
 * Знак меняют при ребрендинге, а не при релизе: до сих пор его правка
 * означала замену public/images/logo-mark.svg и выкладку — то есть
 * разработчика на каждую итерацию фирменного стиля. Пустое значение
 * оставляет знак из коробки, поэтому до первой загрузки шапка
 * выглядит как прежде.
 *
 * Заводится миграцией: сидер наполняет только свежую базу,
 * а на работающем стенде строку пришлось бы заводить руками.
 */
return new class extends Migration
{
    public function up(): void
    {
        if (DB::table('settings')->where('key', Appearance::KEY_LOGO)->exists()) {
            return;
        }

        $now = now();

        DB::table('settings')->insert([
            'group' => 'appearance',
            'key' => Appearance::KEY_LOGO,
            'label' => 'Логотип площадки',
            'description' => 'Знак в шапке, в подвале, на вкладке браузера и в админке. Квадратный, от 512 px; лучше SVG или PNG с прозрачным фоном — знак стоит и на белом, и на тёмно-синем. Пустое поле возвращает знак по умолчанию',
            'type' => 'image',
            'value' => json_encode(''),
            'sort' => 6,
            'created_at' => $now,
            'updated_at' => $now,
        ]);

        Setting::flushCache();
    }

    public function down(): void
    {
        DB::table('settings')->where('key', Appearance::KEY_LOGO)->delete();

        Setting::flushCache();
    }
};
