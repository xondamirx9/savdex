<?php

declare(strict_types=1);

use App\Models\Setting;
use App\Support\Appearance;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Storage;

/**
 * Возврат настройки «Фон первого экрана».
 *
 * Строку удалили из админки, и раздел «Оформление» пропал из списка
 * настроек вместе с возможностью сменить фон. Первая миграция уже
 * выполнена и повторно не сработает, поэтому строка возвращается
 * этой — с той же защитой от дублей.
 *
 * Загруженный файл при удалении строки с диска не пропадает: если
 * в appearance/ лежат картинки, свежайшая подставляется значением —
 * фон возвращается тем же, каким его загружали.
 */
return new class extends Migration
{
    public function up(): void
    {
        if (DB::table('settings')->where('key', Appearance::KEY_HERO)->exists()) {
            return;
        }

        $value = collect(Storage::disk('public')->files('appearance'))
            ->sortByDesc(fn (string $file) => Storage::disk('public')->lastModified($file))
            ->first() ?? '';

        $now = now();

        DB::table('settings')->insert([
            'group' => 'appearance',
            'key' => Appearance::KEY_HERO,
            'label' => 'Фон первого экрана',
            'description' => 'Картинка за заголовком на главной. Широкая горизонтальная, от 1920 px: она обрезается по центру и затемняется, чтобы читался белый текст. Пустое поле возвращает картинку по умолчанию',
            'type' => 'image',
            'value' => json_encode($value),
            'sort' => 5,
            'created_at' => $now,
            'updated_at' => $now,
        ]);

        Setting::flushCache();
    }

    public function down(): void
    {
        // Удалять настройку заново незачем.
    }
};
