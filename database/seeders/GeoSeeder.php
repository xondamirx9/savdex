<?php

declare(strict_types=1);

namespace Database\Seeders;

use App\Models\Country;
use Illuminate\Database\Seeder;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\DB;

/**
 * Страны и города: география площадки, названия — на пяти языках.
 *
 * Страны разделены на два списка. Основные рынки — те, ради которых
 * площадка делается: они стоят первыми в каждом выпадающем списке
 * в заданном здесь порядке. Направления расширения идут следом
 * и между собой сортируются по алфавиту того языка, на котором
 * открыт сайт (Country::listed) — в константе этот порядок задать
 * нельзя: «Египет», «Egypt» и «埃及» стоят в своих азбуках
 * на разных местах.
 */
class GeoSeeder extends Seeder
{
    /** Общий порядковый номер направлений расширения. */
    private const EXPANSION_SORT = 100;

    /** Основные рынки: [код, телефонный код, валюта, [ru, uz, en, zh, tr]] */
    private const CORE = [
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

    /** Направления расширения: тот же состав полей, что у основных рынков. */
    private const EXPANSION = [
        // Ближний Восток и Северная Африка
        ['sa', '+966', 'SAR', ['Саудовская Аравия', 'Saudiya Arabistoni', 'Saudi Arabia', '沙特阿拉伯', 'Suudi Arabistan']],
        ['qa', '+974', 'QAR', ['Катар', 'Qatar', 'Qatar', '卡塔尔', 'Katar']],
        ['kw', '+965', 'KWD', ['Кувейт', 'Quvayt', 'Kuwait', '科威特', 'Kuveyt']],
        ['bh', '+973', 'BHD', ['Бахрейн', 'Bahrayn', 'Bahrain', '巴林', 'Bahreyn']],
        ['om', '+968', 'OMR', ['Оман', 'Ummon', 'Oman', '阿曼', 'Umman']],
        ['iq', '+964', 'IQD', ['Ирак', 'Iroq', 'Iraq', '伊拉克', 'Irak']],
        ['jo', '+962', 'JOD', ['Иордания', 'Iordaniya', 'Jordan', '约旦', 'Ürdün']],
        ['lb', '+961', 'LBP', ['Ливан', 'Livan', 'Lebanon', '黎巴嫩', 'Lübnan']],
        ['il', '+972', 'ILS', ['Израиль', 'Isroil', 'Israel', '以色列', 'İsrail']],
        ['eg', '+20',  'EGP', ['Египет', 'Misr', 'Egypt', '埃及', 'Mısır']],

        // Центральная и Восточная Европа
        ['pl', '+48',  'PLN', ['Польша', 'Polsha', 'Poland', '波兰', 'Polonya']],
        ['cz', '+420', 'CZK', ['Чехия', 'Chexiya', 'Czechia', '捷克', 'Çekya']],
        ['sk', '+421', 'EUR', ['Словакия', 'Slovakiya', 'Slovakia', '斯洛伐克', 'Slovakya']],
        ['hu', '+36',  'HUF', ['Венгрия', 'Vengriya', 'Hungary', '匈牙利', 'Macaristan']],
        ['ro', '+40',  'RON', ['Румыния', 'Ruminiya', 'Romania', '罗马尼亚', 'Romanya']],
        ['bg', '+359', 'BGN', ['Болгария', 'Bolgariya', 'Bulgaria', '保加利亚', 'Bulgaristan']],
        ['rs', '+381', 'RSD', ['Сербия', 'Serbiya', 'Serbia', '塞尔维亚', 'Sırbistan']],
        ['hr', '+385', 'EUR', ['Хорватия', 'Xorvatiya', 'Croatia', '克罗地亚', 'Hırvatistan']],
        ['si', '+386', 'EUR', ['Словения', 'Sloveniya', 'Slovenia', '斯洛文尼亚', 'Slovenya']],

        // Восточная Европа и Балтия
        ['ua', '+380', 'UAH', ['Украина', 'Ukraina', 'Ukraine', '乌克兰', 'Ukrayna']],
        ['md', '+373', 'MDL', ['Молдова', 'Moldova', 'Moldova', '摩尔多瓦', 'Moldova']],
        ['lt', '+370', 'EUR', ['Литва', 'Litva', 'Lithuania', '立陶宛', 'Litvanya']],
        ['lv', '+371', 'EUR', ['Латвия', 'Latviya', 'Latvia', '拉脱维亚', 'Letonya']],
        ['ee', '+372', 'EUR', ['Эстония', 'Estoniya', 'Estonia', '爱沙尼亚', 'Estonya']],
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
        foreach (self::CORE as $sort => $row) {
            $this->country($row, $sort);
        }

        foreach (self::EXPANSION as $row) {
            $this->country($row, self::EXPANSION_SORT);
        }

        $this->command?->info(sprintf(
            'Справочники: %d стран, %d городов',
            count(self::CORE) + count(self::EXPANSION),
            count(self::UZ_CITIES),
        ));
    }

    /**
     * Страна с переводами.
     *
     * Сидер запускается на каждом деплое, поэтому идемпотентен:
     * страна ищется по коду, названия обновляются на месте. Без этого
     * страна, добавленная после прошлого релиза, доезжала бы до прода
     * только пересозданием базы.
     *
     * @param  array{0: string, 1: string, 2: string, 3: list<string>}  $row
     */
    private function country(array $row, int $sort): void
    {
        [$code, $phone, $currency, $names] = $row;

        $country = Country::updateOrCreate(
            ['code' => $code],
            ['phone_code' => $phone, 'currency_code' => $currency, 'sort' => $sort, 'is_active' => true],
        );

        foreach (self::LOCALES as $i => $locale) {
            $country->translations()->updateOrCreate(['locale' => $locale], ['name' => $names[$i]]);
        }

        if ($code === 'uz') {
            $this->seedUzCities($country->id, now());
        }
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
