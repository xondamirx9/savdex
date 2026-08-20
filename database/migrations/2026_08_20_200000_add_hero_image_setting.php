<?php

declare(strict_types=1);

use App\Models\Setting;
use App\Support\Appearance;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Фон первого экрана — настройкой, а не файлом в репозитории.
 *
 * Картинку на витрине меняют, когда меняется рекламная кампания,
 * а не когда выходит релиз. Пустое значение оставляет картинку
 * из коробки, поэтому до первой загрузки витрина выглядит как
 * прежде.
 *
 * Заводится миграцией: сидер наполняет только свежую базу,
 * а на работающем стенде строку пришлось бы заводить руками.
 */
return new class extends Migration
{
    public function up(): void
    {
        if (DB::table('settings')->where('key', Appearance::KEY_HERO)->exists()) {
            return;
        }

        $now = now();

        DB::table('settings')->insert([
            'group' => 'appearance',
            'key' => Appearance::KEY_HERO,
            'label' => 'Фон первого экрана',
            'description' => 'Картинка за заголовком на главной. Широкая горизонтальная, от 1920 px: она обрезается по центру и затемняется, чтобы читался белый текст. Пустое поле возвращает картинку по умолчанию',
            'type' => 'image',
            'value' => json_encode(''),
            'sort' => 5,
            'created_at' => $now,
            'updated_at' => $now,
        ]);

        Setting::flushCache();
    }

    public function down(): void
    {
        DB::table('settings')->where('key', Appearance::KEY_HERO)->delete();

        Setting::flushCache();
    }
};
