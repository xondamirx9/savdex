<?php

declare(strict_types=1);

use App\Models\Setting;
use App\Support\Locales;
use App\Support\PriceDisplay;
use Illuminate\Database\Migrations\Migration;
use Illuminate\Support\Facades\DB;

/**
 * Валюта показа цен по языкам витрины — в настройках площадки.
 *
 * Сидер наполняет только свежую базу; на работающем стенде настройки
 * заводит миграция. Значения — валюты по умолчанию из PriceDisplay:
 * русская и узбекская версии в сумах, английская в долларах,
 * китайская в юанях, турецкая в лирах.
 */
return new class extends Migration
{
    public function up(): void
    {
        $now = now();
        $sort = (int) DB::table('settings')->max('sort') + 1;

        foreach (PriceDisplay::DEFAULTS as $locale => $currency) {
            $key = PriceDisplay::key($locale);

            // Настройку, заведённую до миграции руками, не трогаем:
            // перезапись вернула бы админке значение по умолчанию
            if (DB::table('settings')->where('key', $key)->exists()) {
                continue;
            }

            DB::table('settings')->insert([
                'group' => 'currency',
                'key' => $key,
                'label' => 'Валюта на версии «'.Locales::ALL[$locale]['label'].'»',
                'description' => 'Код валюты, в которой посетители этой языковой версии видят цены: UZS, USD, EUR, CNY, TRY, RUB, KZT. '
                    .'Цена продавца остаётся в его валюте, пересчёт по курсу ЦБ показывается рядом со знаком «≈»',
                'type' => 'string',
                'value' => json_encode($currency),
                'sort' => $sort++,
                'created_at' => $now,
                'updated_at' => $now,
            ]);
        }

        // Настройки читаются из кэша на сутки: без сброса витрина
        // не увидела бы новые до завтра
        Setting::flushCache();
    }

    public function down(): void
    {
        DB::table('settings')
            ->whereIn('key', array_map(PriceDisplay::key(...), array_keys(PriceDisplay::DEFAULTS)))
            ->delete();

        Setting::flushCache();
    }
};
