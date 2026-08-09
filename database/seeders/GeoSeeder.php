<?php

declare(strict_types=1);

namespace Database\Seeders;

use Illuminate\Database\Seeder;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;

/**
 * Страны и города по §17 п.5 ТЗ: 9 стран, города Узбекистана.
 * Названия хранятся в переводах — интерфейс на 5 языках.
 */
class GeoSeeder extends Seeder
{
    /** [код, телефонный код, валюта, [ru, uz, en, zh, tr]] */
    private const COUNTRIES = [
        ['uz', '+998', 'UZS', ['Узбекистан', 'Oʻzbekiston', 'Uzbekistan', '乌兹别克斯坦', 'Özbekistan']],
        ['kz', '+7',   'KZT', ['Казахстан', 'Qozogʻiston', 'Kazakhstan', '哈萨克斯坦', 'Kazakistan']],
        ['kg', '+996', 'KGS', ['Кыргызстан', 'Qirgʻiziston', 'Kyrgyzstan', '吉尔吉斯斯坦', 'Kırgızistan']],
        ['tj', '+992', 'TJS', ['Таджикистан', 'Tojikiston', 'Tajikistan', '塔吉克斯坦', 'Tacikistan']],
        ['cn', '+86',  'CNY', ['Китай', 'Xitoy', 'China', '中国', 'Çin']],
        ['tr', '+90',  'TRY', ['Турция', 'Turkiya', 'Türkiye', '土耳其', 'Türkiye']],
        ['ru', '+7',   'RUB', ['Россия', 'Rossiya', 'Russia', '俄罗斯', 'Rusya']],
        ['ae', '+971', 'AED', ['ОАЭ', 'BAA', 'UAE', '阿联酋', 'BAE']],
        ['in', '+91',  'INR', ['Индия', 'Hindiston', 'India', '印度', 'Hindistan']],
    ];

    /** Города Узбекистана: [slug, lat, lng, [ru, uz, en, zh, tr]] */
    private const UZ_CITIES = [
        ['tashkent',   41.2995, 69.2401, ['Ташкент', 'Toshkent', 'Tashkent', '塔什干', 'Taşkent']],
        ['samarkand',  39.6270, 66.9750, ['Самарканд', 'Samarqand', 'Samarkand', '撒马尔罕', 'Semerkant']],
        ['bukhara',    39.7747, 64.4286, ['Бухара', 'Buxoro', 'Bukhara', '布哈拉', 'Buhara']],
        ['andijan',    40.7821, 72.3442, ['Андижан', 'Andijon', 'Andijan', '安集延', 'Andican']],
        ['namangan',   40.9983, 71.6726, ['Наманган', 'Namangan', 'Namangan', '纳曼干', 'Namangan']],
        ['fergana',    40.3864, 71.7864, ['Фергана', 'Fargʻona', 'Fergana', '费尔干纳', 'Fergana']],
        ['nukus',      42.4531, 59.6103, ['Нукус', 'Nukus', 'Nukus', '努库斯', 'Nukus']],
        ['karshi',     38.8606, 65.7891, ['Карши', 'Qarshi', 'Karshi', '卡尔希', 'Karşı']],
        ['navoiy',     40.0844, 65.3792, ['Навои', 'Navoiy', 'Navoiy', '纳沃伊', 'Nevai']],
        ['jizzakh',    40.1158, 67.8422, ['Джизак', 'Jizzax', 'Jizzakh', '吉扎克', 'Cizzah']],
        ['termez',     37.2242, 67.2783, ['Термез', 'Termiz', 'Termez', '铁尔梅兹', 'Termez']],
        ['urgench',    41.5500, 60.6333, ['Ургенч', 'Urganch', 'Urgench', '乌尔根奇', 'Ürgenç']],
        ['gulistan',   40.4897, 68.7842, ['Гулистан', 'Guliston', 'Gulistan', '古利斯坦', 'Gülistan']],
        ['bekabad',    40.2206, 69.2686, ['Бекабад', 'Bekobod', 'Bekabad', '别卡巴德', 'Bekabad']],
    ];

    private const LOCALES = ['ru', 'uz', 'en', 'zh', 'tr'];

    public function run(): void
    {
        $now = now();

        foreach (self::COUNTRIES as $i => [$code, $phone, $currency, $names]) {
            $countryId = DB::table('countries')->updateOrInsert(
                ['code' => $code],
                [
                    'phone_code' => $phone,
                    'currency_code' => $currency,
                    'sort' => $i,
                    'is_active' => true,
                    'updated_at' => $now,
                    'created_at' => $now,
                ],
            );

            $countryId = DB::table('countries')->where('code', $code)->value('id');

            foreach (self::LOCALES as $j => $locale) {
                DB::table('country_translations')->updateOrInsert(
                    ['country_id' => $countryId, 'locale' => $locale],
                    ['name' => $names[$j], 'updated_at' => $now, 'created_at' => $now],
                );
            }

            if ($code === 'uz') {
                $this->seedUzCities($countryId, $now);
            }
        }

        $this->command?->info(sprintf(
            'Справочники: %d стран, %d городов',
            count(self::COUNTRIES),
            count(self::UZ_CITIES),
        ));
    }

    private function seedUzCities(int $countryId, Carbon $now): void
    {
        foreach (self::UZ_CITIES as $i => [$slug, $lat, $lng, $names]) {
            DB::table('cities')->updateOrInsert(
                ['country_id' => $countryId, 'slug' => $slug],
                [
                    'lat' => $lat,
                    'lng' => $lng,
                    'sort' => $i,
                    'is_active' => true,
                    'updated_at' => $now,
                    'created_at' => $now,
                ],
            );

            $cityId = DB::table('cities')
                ->where('country_id', $countryId)
                ->where('slug', $slug)
                ->value('id');

            foreach (self::LOCALES as $j => $locale) {
                DB::table('city_translations')->updateOrInsert(
                    ['city_id' => $cityId, 'locale' => $locale],
                    ['name' => $names[$j], 'updated_at' => $now, 'created_at' => $now],
                );
            }
        }
    }
}
