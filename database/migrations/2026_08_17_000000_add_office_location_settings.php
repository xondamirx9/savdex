<?php

declare(strict_types=1);

use App\Models\Setting;
use App\Support\OfficeLocation;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Координаты офиса и масштаб карты в настройках площадки.
 *
 * Сидер наполняет только свежую базу — на уже работающем стенде новые
 * настройки не появились бы вовсе, и раздел «Офис на карте» на странице
 * «О компании» пришлось бы включать, заводя строки в админке руками.
 *
 * Координаты заводятся пустыми. Подставить сюда центр Ташкента было бы
 * заманчиво — карта заработала бы сразу после деплоя, — но метка стояла
 * бы не там, где офис, а на витрине это выдуманный факт. Пока настройка
 * пуста, показывается один адрес, без карты.
 */
return new class extends Migration
{
    /** @var list<array{key: string, label: string, type: string, value: mixed, description: string, sort: int}> */
    private const SETTINGS = [
        [
            'key' => OfficeLocation::KEY_COORDS,
            'label' => 'Координаты офиса',
            'type' => 'string',
            'value' => '',
            'description' => 'Широта и долгота через запятую, например: 41.311081, 69.240562. Взять их можно так: открыть Яндекс.Карты или Google Maps, нажать на здание правой кнопкой и скопировать координаты. Пока поле пустое, карта на странице не показывается — виден только адрес',
            'sort' => 6,
        ],
        [
            'key' => OfficeLocation::KEY_ZOOM,
            'label' => 'Масштаб карты',
            'type' => 'number',
            'value' => 16,
            'description' => 'От 3 до 19. 16 — дом и соседние кварталы, 12 — город целиком',
            'sort' => 7,
        ],
    ];

    public function up(): void
    {
        $now = now();

        foreach (self::SETTINGS as $setting) {
            // Настройку, заведённую до миграции руками, не трогаем:
            // перезапись вернула бы админке значение по умолчанию
            if (DB::table('settings')->where('key', $setting['key'])->exists()) {
                continue;
            }

            DB::table('settings')->insert([
                'group' => 'contacts',
                'key' => $setting['key'],
                'label' => $setting['label'],
                'description' => $setting['description'],
                'type' => $setting['type'],
                'value' => json_encode($setting['value']),
                'sort' => $setting['sort'],
                'created_at' => $now,
                'updated_at' => $now,
            ]);
        }

        /*
         * Адрес офиса в базе уже был, но лежал без дела: до этой
         * миграции его никто не читал. Пояснение объясняет тому, кто
         * откроет настройку, где он теперь виден.
         */
        DB::table('settings')
            ->where('key', OfficeLocation::KEY_ADDRESS)
            ->whereNull('description')
            ->update([
                'description' => 'Показывается в разделе «Офис на карте» на странице «О компании». Пустой адрес и пустые координаты убирают раздел со страницы целиком',
                'updated_at' => $now,
            ]);

        // Настройки читаются из кэша на сутки: без сброса раздел
        // появился бы на витрине не сразу после деплоя
        Setting::flushCache();
    }

    public function down(): void
    {
        DB::table('settings')
            ->whereIn('key', array_column(self::SETTINGS, 'key'))
            ->delete();

        Setting::flushCache();
    }
};
