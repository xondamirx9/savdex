<?php

declare(strict_types=1);

namespace Database\Seeders;

use App\Models\City;
use App\Models\Country;
use Illuminate\Database\Seeder;

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

    /**
     * Города по странам: код страны → [slug, широта, долгота, [ru, uz, en, zh, tr]].
     *
     * Это не полный справочник населённых пунктов, а список мест, где
     * компания может сидеть: столица, крупные города, промышленные
     * узлы и порты. Порядок внутри страны — по значимости: он же
     * становится порядком в выпадающем списке.
     *
     * Координаты нигде на сайте пока не показываются и лежат про запас
     * — под карту поставщиков. Проверяются тестом на попадание
     * в границы своей страны: перепутанные местами широта и долгота
     * иначе всплыли бы уже на карте.
     */
    private const CITIES = [
        'uz' => [
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
        ],
        'kz' => [
            ['almaty',   43.2220, 76.8512, ['Алматы', 'Almati', 'Almaty', '阿拉木图', 'Almatı']],
            ['astana',   51.1694, 71.4491, ['Астана', 'Astana', 'Astana', '阿斯塔纳', 'Astana']],
            ['shymkent', 42.3417, 69.5901, ['Шымкент', 'Chimkent', 'Shymkent', '奇姆肯特', 'Şımkent']],
            ['karaganda', 49.8047, 73.1094, ['Караганда', 'Qarag\'anda', 'Karaganda', '卡拉干达', 'Karagandı']],
            ['aktobe',   50.2839, 57.1670, ['Актобе', 'Aqtobe', 'Aktobe', '阿克托别', 'Aktöbe']],
            ['atyrau',   47.0945, 51.9238, ['Атырау', 'Atirau', 'Atyrau', '阿特劳', 'Atırau']],
            ['aktau',    43.6481, 51.1722, ['Актау', 'Aqtau', 'Aktau', '阿克套', 'Aktau']],
            ['pavlodar', 52.2873, 76.9674, ['Павлодар', 'Pavlodar', 'Pavlodar', '巴甫洛达尔', 'Pavlodar']],
            ['taraz',    42.9000, 71.3667, ['Тараз', 'Taraz', 'Taraz', '塔拉兹', 'Taraz']],
            ['oskemen',  49.9714, 82.6059, ['Усть-Каменогорск', 'Oskemen', 'Oskemen', '乌斯季卡缅诺戈尔斯克', 'Öskemen']],
            ['kostanay', 53.2198, 63.6354, ['Костанай', 'Qostanay', 'Kostanay', '科斯塔奈', 'Kostanay']],
            ['kyzylorda', 44.8479, 65.5093, ['Кызылорда', 'Qizilo\'rda', 'Kyzylorda', '克孜勒奥尔达', 'Kızılorda']],
            ['uralsk',   51.2333, 51.3667, ['Уральск', 'Uralsk', 'Uralsk', '乌拉尔斯克', 'Uralsk']],
        ],

        'kg' => [
            ['bishkek',   42.8746, 74.5698, ['Бишкек', 'Bishkek', 'Bishkek', '比什凯克', 'Bişkek']],
            ['osh',       40.5283, 72.7985, ['Ош', 'O\'sh', 'Osh', '奥什', 'Oş']],
            ['jalal-abad', 40.9333, 72.9833, ['Джалал-Абад', 'Jalolobod', 'Jalal-Abad', '贾拉拉巴德', 'Celalabat']],
            ['tokmok',    42.8393, 75.2819, ['Токмок', 'Tokmok', 'Tokmok', '托克马克', 'Tokmak']],
            ['karakol',   42.4907, 78.3936, ['Каракол', 'Karakol', 'Karakol', '卡拉科尔', 'Karakol']],
            ['naryn',     41.4287, 75.9911, ['Нарын', 'Naryn', 'Naryn', '纳伦', 'Narın']],
            ['batken',    40.0626, 70.8199, ['Баткен', 'Batken', 'Batken', '巴特肯', 'Batken']],
        ],

        'tj' => [
            ['dushanbe',  38.5598, 68.7870, ['Душанбе', 'Dushanbe', 'Dushanbe', '杜尚别', 'Duşanbe']],
            ['khujand',   40.2833, 69.6222, ['Худжанд', 'Xo\'jand', 'Khujand', '苦盏', 'Hucend']],
            ['bokhtar',   37.8361, 68.7803, ['Бохтар', 'Boxtar', 'Bokhtar', '博赫塔尔', 'Bohtar']],
            ['kulob',     37.9092, 69.7822, ['Куляб', 'Kulob', 'Kulob', '库利亚布', 'Kulob']],
            ['tursunzoda', 38.5103, 68.2297, ['Турсунзаде', 'Tursunzoda', 'Tursunzoda', '图尔孙扎达', 'Tursunzade']],
            ['panjakent', 39.4953, 67.6089, ['Пенджикент', 'Panjikent', 'Panjakent', '片治肯特', 'Pencikent']],
        ],

        'cn' => [
            ['beijing',  39.9042, 116.4074, ['Пекин', 'Pekin', 'Beijing', '北京', 'Pekin']],
            ['shanghai', 31.2304, 121.4737, ['Шанхай', 'Shanxay', 'Shanghai', '上海', 'Şanghay']],
            ['guangzhou', 23.1291, 113.2644, ['Гуанчжоу', 'Guanchjou', 'Guangzhou', '广州', 'Guangzhou']],
            ['shenzhen', 22.5431, 114.0579, ['Шэньчжэнь', 'Shenchjen', 'Shenzhen', '深圳', 'Shenzhen']],
            ['yiwu',     29.3069, 120.0745, ['Иу', 'Iu', 'Yiwu', '义乌', 'Yiwu']],
            ['urumqi',   43.8256, 87.6168, ['Урумчи', 'Urumchi', 'Urumqi', '乌鲁木齐', 'Ürümçi']],
            ['hangzhou', 30.2741, 120.1551, ['Ханчжоу', 'Xanchjou', 'Hangzhou', '杭州', 'Hangzhou']],
            ['tianjin',  39.0842, 117.2009, ['Тяньцзинь', 'Tyantszin', 'Tianjin', '天津', 'Tiencin']],
            ['chongqing', 29.5630, 106.5516, ['Чунцин', 'Chuntsin', 'Chongqing', '重庆', 'Çongçing']],
            ['chengdu',  30.5728, 104.0668, ['Чэнду', 'Chendu', 'Chengdu', '成都', 'Chengdu']],
            ['suzhou',   31.2989, 120.5853, ['Сучжоу', 'Suchjou', 'Suzhou', '苏州', 'Suzhou']],
            ['qingdao',  36.0671, 120.3826, ['Циндао', 'Sindao', 'Qingdao', '青岛', 'Qingdao']],
            ['ningbo',   29.8683, 121.5440, ['Нинбо', 'Ningbo', 'Ningbo', '宁波', 'Ningbo']],
            ['dongguan', 23.0209, 113.7518, ['Дунгуань', 'Dunguan', 'Dongguan', '东莞', 'Dongguan']],
            ['foshan',   23.0219, 113.1214, ['Фошань', 'Foshan', 'Foshan', '佛山', 'Foshan']],
            ['wuhan',    30.5928, 114.3055, ['Ухань', 'Uxan', 'Wuhan', '武汉', 'Vuhan']],
            ['xian',     34.3416, 108.9398, ['Сиань', 'Sian', 'Xi\'an', '西安', 'Xi\'an']],
            ['zhengzhou', 34.7466, 113.6254, ['Чжэнчжоу', 'Chjenchjou', 'Zhengzhou', '郑州', 'Zhengzhou']],
            ['nanjing',  32.0603, 118.7969, ['Нанкин', 'Nankin', 'Nanjing', '南京', 'Nankin']],
            ['dalian',   38.9140, 121.6147, ['Далянь', 'Dalyan', 'Dalian', '大连', 'Dalian']],
            ['xiamen',   24.4798, 118.0894, ['Сямынь', 'Syamin', 'Xiamen', '厦门', 'Xiamen']],
            ['shenyang', 41.8057, 123.4315, ['Шэньян', 'Shenyan', 'Shenyang', '沈阳', 'Şenyang']],
            ['wenzhou',  27.9938, 120.6994, ['Вэньчжоу', 'Venchjou', 'Wenzhou', '温州', 'Wenzhou']],
            ['kashgar',  39.4704, 75.9898, ['Кашгар', 'Qashqar', 'Kashgar', '喀什', 'Kaşgar']],
        ],

        'tr' => [
            ['istanbul',     41.0082, 28.9784, ['Стамбул', 'Istanbul', 'Istanbul', '伊斯坦布尔', 'İstanbul']],
            ['ankara',       39.9334, 32.8597, ['Анкара', 'Anqara', 'Ankara', '安卡拉', 'Ankara']],
            ['izmir',        38.4237, 27.1428, ['Измир', 'Izmir', 'Izmir', '伊兹密尔', 'İzmir']],
            ['bursa',        40.1826, 29.0665, ['Бурса', 'Bursa', 'Bursa', '布尔萨', 'Bursa']],
            ['gaziantep',    37.0662, 37.3833, ['Газиантеп', 'Gaziantep', 'Gaziantep', '加济安泰普', 'Gaziantep']],
            ['izmit',        40.7654, 29.9408, ['Измит', 'Izmit', 'Izmit', '伊兹米特', 'İzmit']],
            ['adana',        37.0000, 35.3213, ['Адана', 'Adana', 'Adana', '阿达纳', 'Adana']],
            ['konya',        37.8746, 32.4932, ['Конья', 'Konya', 'Konya', '科尼亚', 'Konya']],
            ['mersin',       36.8121, 34.6415, ['Мерсин', 'Mersin', 'Mersin', '梅尔辛', 'Mersin']],
            ['kayseri',      38.7312, 35.4787, ['Кайсери', 'Kayseri', 'Kayseri', '开塞利', 'Kayseri']],
            ['antalya',      36.8969, 30.7133, ['Анталья', 'Antaliya', 'Antalya', '安塔利亚', 'Antalya']],
            ['denizli',      37.7765, 29.0864, ['Денизли', 'Denizli', 'Denizli', '代尼兹利', 'Denizli']],
            ['eskisehir',    39.7767, 30.5206, ['Эскишехир', 'Eskishehir', 'Eskisehir', '埃斯基谢希尔', 'Eskişehir']],
            ['manisa',       38.6191, 27.4289, ['Маниса', 'Manisa', 'Manisa', '马尼萨', 'Manisa']],
            ['samsun',       41.2867, 36.3300, ['Самсун', 'Samsun', 'Samsun', '萨姆松', 'Samsun']],
            ['iskenderun',   36.5872, 36.1731, ['Искендерун', 'Iskenderun', 'Iskenderun', '伊斯肯德伦', 'İskenderun']],
            ['trabzon',      41.0015, 39.7178, ['Трабзон', 'Trabzon', 'Trabzon', '特拉布宗', 'Trabzon']],
            ['kahramanmaras', 37.5858, 36.9371, ['Кахраманмараш', 'Kahramanmarash', 'Kahramanmaras', '卡赫拉曼马拉什', 'Kahramanmaraş']],
        ],

        'ru' => [
            ['moscow',          55.7558, 37.6173, ['Москва', 'Moskva', 'Moscow', '莫斯科', 'Moskova']],
            ['saint-petersburg', 59.9311, 30.3609, ['Санкт-Петербург', 'Sankt-Peterburg', 'Saint Petersburg', '圣彼得堡', 'Sankt-Peterburg']],
            ['novosibirsk',     55.0084, 82.9357, ['Новосибирск', 'Novosibirsk', 'Novosibirsk', '新西伯利亚', 'Novosibirsk']],
            ['yekaterinburg',   56.8389, 60.6057, ['Екатеринбург', 'Yekaterinburg', 'Yekaterinburg', '叶卡捷琳堡', 'Yekaterinburg']],
            ['kazan',           55.7963, 49.1064, ['Казань', 'Qozon', 'Kazan', '喀山', 'Kazan']],
            ['nizhny-novgorod', 56.3269, 44.0059, ['Нижний Новгород', 'Nijniy Novgorod', 'Nizhny Novgorod', '下诺夫哥罗德', 'Nijni Novgorod']],
            ['krasnodar',       45.0355, 38.9753, ['Краснодар', 'Krasnodar', 'Krasnodar', '克拉斯诺达尔', 'Krasnodar']],
            ['rostov-on-don',   47.2357, 39.7015, ['Ростов-на-Дону', 'Rostov-na-Donu', 'Rostov-on-Don', '顿河畔罗斯托夫', 'Rostov-na-Donu']],
            ['samara',          53.1959, 50.1002, ['Самара', 'Samara', 'Samara', '萨马拉', 'Samara']],
            ['chelyabinsk',     55.1644, 61.4368, ['Челябинск', 'Chelyabinsk', 'Chelyabinsk', '车里雅宾斯克', 'Çelyabinsk']],
            ['ufa',             54.7388, 55.9721, ['Уфа', 'Ufa', 'Ufa', '乌法', 'Ufa']],
            ['krasnoyarsk',     56.0153, 92.8932, ['Красноярск', 'Krasnoyarsk', 'Krasnoyarsk', '克拉斯诺亚尔斯克', 'Krasnoyarsk']],
            ['perm',            58.0105, 56.2502, ['Пермь', 'Perm', 'Perm', '彼尔姆', 'Perm']],
            ['voronezh',        51.6720, 39.1843, ['Воронеж', 'Voronej', 'Voronezh', '沃罗涅日', 'Voronej']],
            ['volgograd',       48.7071, 44.5170, ['Волгоград', 'Volgograd', 'Volgograd', '伏尔加格勒', 'Volgograd']],
            ['omsk',            54.9885, 73.3242, ['Омск', 'Omsk', 'Omsk', '鄂木斯克', 'Omsk']],
            ['vladivostok',     43.1198, 131.8869, ['Владивосток', 'Vladivostok', 'Vladivostok', '符拉迪沃斯托克', 'Vladivostok']],
            ['saratov',         51.5336, 46.0343, ['Саратов', 'Saratov', 'Saratov', '萨拉托夫', 'Saratov']],
            ['tyumen',          57.1530, 65.5343, ['Тюмень', 'Tyumen', 'Tyumen', '秋明', 'Tümen']],
            ['tolyatti',        53.5167, 49.4000, ['Тольятти', 'Tolyatti', 'Tolyatti', '陶里亚蒂', 'Togliatti']],
            ['izhevsk',         56.8526, 53.2045, ['Ижевск', 'Ijevsk', 'Izhevsk', '伊热夫斯克', 'İjevsk']],
            ['barnaul',         53.3547, 83.7697, ['Барнаул', 'Barnaul', 'Barnaul', '巴尔瑙尔', 'Barnaul']],
            ['irkutsk',         52.2870, 104.3050, ['Иркутск', 'Irkutsk', 'Irkutsk', '伊尔库茨克', 'İrkutsk']],
            ['khabarovsk',      48.4827, 135.0838, ['Хабаровск', 'Xabarovsk', 'Khabarovsk', '哈巴罗夫斯克', 'Habarovsk']],
            ['yaroslavl',       57.6261, 39.8845, ['Ярославль', 'Yaroslavl', 'Yaroslavl', '雅罗斯拉夫尔', 'Yaroslavl']],
            ['tula',            54.1961, 37.6182, ['Тула', 'Tula', 'Tula', '图拉', 'Tula']],
            ['orenburg',        51.7727, 55.0988, ['Оренбург', 'Orenburg', 'Orenburg', '奥伦堡', 'Orenburg']],
            ['magnitogorsk',    53.4186, 59.0472, ['Магнитогорск', 'Magnitogorsk', 'Magnitogorsk', '马格尼托哥尔斯克', 'Magnitogorsk']],
            ['novokuznetsk',    53.7557, 87.1099, ['Новокузнецк', 'Novokuznetsk', 'Novokuznetsk', '新库兹涅茨克', 'Novokuznetsk']],
            ['astrakhan',       46.3497, 48.0408, ['Астрахань', 'Astraxan', 'Astrakhan', '阿斯特拉罕', 'Astrahan']],
            ['novorossiysk',    44.7239, 37.7686, ['Новороссийск', 'Novorossiysk', 'Novorossiysk', '新罗西斯克', 'Novorossiysk']],
            ['kaliningrad',     54.7104, 20.4522, ['Калининград', 'Kaliningrad', 'Kaliningrad', '加里宁格勒', 'Kaliningrad']],
            ['murmansk',        68.9585, 33.0827, ['Мурманск', 'Murmansk', 'Murmansk', '摩尔曼斯克', 'Murmansk']],
            ['blagoveshchensk', 50.2907, 127.5272, ['Благовещенск', 'Blagoveshchensk', 'Blagoveshchensk', '布拉戈维申斯克', 'Blagoveşçensk']],
        ],

        'ae' => [
            ['dubai',         25.2048, 55.2708, ['Дубай', 'Dubay', 'Dubai', '迪拜', 'Dubai']],
            ['abu-dhabi',     24.4539, 54.3773, ['Абу-Даби', 'Abu-Dabi', 'Abu Dhabi', '阿布扎比', 'Abu Dabi']],
            ['sharjah',       25.3463, 55.4211, ['Шарджа', 'Sharja', 'Sharjah', '沙迦', 'Şarika']],
            ['ajman',         25.4052, 55.5136, ['Аджман', 'Ajmon', 'Ajman', '阿治曼', 'Acman']],
            ['ras-al-khaimah', 25.7895, 55.9432, ['Рас-эль-Хайма', 'Ras al-Xayma', 'Ras Al Khaimah', '哈伊马角', 'Re\'sülhayme']],
            ['fujairah',      25.1288, 56.3265, ['Фуджейра', 'Fujayra', 'Fujairah', '富查伊拉', 'Füceyre']],
            ['al-ain',        24.2075, 55.7447, ['Эль-Айн', 'Al-Ayn', 'Al Ain', '艾因', 'El Ayn']],
        ],

        'in' => [
            ['delhi',        28.6139, 77.2090, ['Дели', 'Dehli', 'Delhi', '德里', 'Delhi']],
            ['mumbai',       19.0760, 72.8777, ['Мумбаи', 'Mumbay', 'Mumbai', '孟买', 'Mumbai']],
            ['bengaluru',    12.9716, 77.5946, ['Бангалор', 'Bangalor', 'Bengaluru', '班加罗尔', 'Bengaluru']],
            ['chennai',      13.0827, 80.2707, ['Ченнаи', 'Chennay', 'Chennai', '金奈', 'Chennai']],
            ['kolkata',      22.5726, 88.3639, ['Калькутта', 'Kalkutta', 'Kolkata', '加尔各答', 'Kalküta']],
            ['hyderabad',    17.3850, 78.4867, ['Хайдарабад', 'Haydarobod', 'Hyderabad', '海得拉巴', 'Haydarabad']],
            ['ahmedabad',    23.0225, 72.5714, ['Ахмадабад', 'Ahmadobod', 'Ahmedabad', '艾哈迈达巴德', 'Ahmedabad']],
            ['pune',         18.5204, 73.8567, ['Пуна', 'Puna', 'Pune', '浦那', 'Pune']],
            ['surat',        21.1702, 72.8311, ['Сурат', 'Surat', 'Surat', '苏拉特', 'Surat']],
            ['jaipur',       26.9124, 75.7873, ['Джайпур', 'Jaypur', 'Jaipur', '斋浦尔', 'Jaipur']],
            ['gurugram',     28.4595, 77.0266, ['Гуруграм', 'Gurugram', 'Gurugram', '古尔冈', 'Gurugram']],
            ['noida',        28.5355, 77.3910, ['Нойда', 'Noyda', 'Noida', '诺伊达', 'Noida']],
            ['coimbatore',   11.0168, 76.9558, ['Коимбатур', 'Koimbatur', 'Coimbatore', '哥印拜陀', 'Coimbatore']],
            ['ludhiana',     30.9010, 75.8573, ['Лудхияна', 'Ludhiana', 'Ludhiana', '卢迪亚纳', 'Ludhiana']],
            ['kochi',        9.9312, 76.2673, ['Кочин', 'Kochin', 'Kochi', '科钦', 'Kochi']],
            ['kanpur',       26.4499, 80.3319, ['Канпур', 'Kanpur', 'Kanpur', '坎普尔', 'Kanpur']],
            ['nagpur',       21.1458, 79.0882, ['Нагпур', 'Nagpur', 'Nagpur', '那格浦尔', 'Nagpur']],
            ['visakhapatnam', 17.6868, 83.2185, ['Вишакхапатнам', 'Vishakxapatnam', 'Visakhapatnam', '维沙卡帕特南', 'Visakhapatnam']],
            ['indore',       22.7196, 75.8577, ['Индор', 'Indor', 'Indore', '印多尔', 'Indore']],
            ['lucknow',      26.8467, 80.9462, ['Лакхнау', 'Lakhnau', 'Lucknow', '勒克瑙', 'Lucknow']],
        ],

        'sa' => [
            ['riyadh',   24.7136, 46.6753, ['Эр-Рияд', 'Ar-Riyod', 'Riyadh', '利雅得', 'Riyad']],
            ['jeddah',   21.4858, 39.1925, ['Джидда', 'Jidda', 'Jeddah', '吉达', 'Cidde']],
            ['dammam',   26.4207, 50.0888, ['Даммам', 'Dammam', 'Dammam', '达曼', 'Dammam']],
            ['al-khobar', 26.2794, 50.2083, ['Эль-Хубар', 'Al-Xubar', 'Al Khobar', '胡拜尔', 'Khobar']],
            ['jubail',   27.0046, 49.6461, ['Эль-Джубайль', 'Jubayl', 'Jubail', '朱拜勒', 'Jubail']],
            ['dhahran',  26.2886, 50.1140, ['Дахран', 'Dahran', 'Dhahran', '宰赫兰', 'Dahran']],
            ['mecca',    21.3891, 39.8579, ['Мекка', 'Makka', 'Mecca', '麦加', 'Mekke']],
            ['medina',   24.4672, 39.6111, ['Медина', 'Madina', 'Medina', '麦地那', 'Medine']],
            ['yanbu',    24.0895, 38.0637, ['Янбу', 'Yanbu', 'Yanbu', '延布', 'Yanbu']],
            ['taif',     21.2703, 40.4158, ['Эт-Таиф', 'Toif', 'Taif', '塔伊夫', 'Taif']],
            ['buraydah', 26.3260, 43.9750, ['Бурайда', 'Burayda', 'Buraydah', '布赖代', 'Bureyde']],
            ['tabuk',    28.3835, 36.5662, ['Табук', 'Tabuk', 'Tabuk', '塔布克', 'Tebük']],
        ],

        'qa' => [
            ['doha',      25.2854, 51.5310, ['Доха', 'Doha', 'Doha', '多哈', 'Doha']],
            ['al-rayyan', 25.2919, 51.4244, ['Эр-Райян', 'Ar-Rayyon', 'Al Rayyan', '赖扬', 'Reyyan']],
            ['lusail',    25.4281, 51.4906, ['Лусаил', 'Lusail', 'Lusail', '卢塞尔', 'Lusail']],
            ['al-wakrah', 25.1659, 51.6032, ['Эль-Вакра', 'Al-Vakra', 'Al Wakrah', '沃克拉', 'Vakra']],
            ['ras-laffan', 25.9000, 51.5500, ['Рас-Лаффан', 'Ras-Laffan', 'Ras Laffan', '拉斯拉凡', 'Ras Laffan']],
        ],

        'kw' => [
            ['kuwait-city',  29.3759, 47.9774, ['Эль-Кувейт', 'Quvayt', 'Kuwait City', '科威特城', 'Kuveyt']],
            ['hawalli',      29.3328, 48.0286, ['Хавалли', 'Havalli', 'Hawalli', '哈瓦利', 'Havalli']],
            ['al-ahmadi',    29.0769, 48.0838, ['Эль-Ахмади', 'Al-Ahmadi', 'Al Ahmadi', '艾哈迈迪', 'Ahmedi']],
            ['al-farwaniyah', 29.2775, 47.9589, ['Эль-Фарвания', 'Al-Farvaniya', 'Al Farwaniyah', '法尔瓦尼耶', 'Farvaniye']],
            ['al-jahra',     29.3375, 47.6581, ['Эль-Джахра', 'Al-Jahra', 'Al Jahra', '杰赫拉', 'Cehra']],
        ],

        'bh' => [
            ['manama',  26.2285, 50.5860, ['Манама', 'Manama', 'Manama', '麦纳麦', 'Manama']],
            ['riffa',   26.1300, 50.5550, ['Эр-Рифа', 'Ar-Riffa', 'Riffa', '里法', 'Riffa']],
            ['muharraq', 26.2572, 50.6119, ['Мухаррак', 'Muharraq', 'Muharraq', '穆哈拉格', 'Muharrak']],
            ['isa-town', 26.1736, 50.5478, ['Мадинат-Иса', 'Iso shahri', 'Isa Town', '伊萨城', 'Isa Town']],
        ],

        'om' => [
            ['muscat', 23.5880, 58.3829, ['Маскат', 'Maskat', 'Muscat', '马斯喀特', 'Maskat']],
            ['sohar',  24.3477, 56.7089, ['Сохар', 'Sohar', 'Sohar', '苏哈尔', 'Suhar']],
            ['salalah', 17.0197, 54.0897, ['Салала', 'Salala', 'Salalah', '塞拉莱', 'Salala']],
            ['duqm',   19.6500, 57.7050, ['Дукм', 'Duqm', 'Duqm', '杜库姆', 'Dukm']],
            ['nizwa',  22.9333, 57.5333, ['Низва', 'Nizva', 'Nizwa', '尼兹瓦', 'Nizva']],
            ['sur',    22.5667, 59.5289, ['Сур', 'Sur', 'Sur', '苏尔', 'Sur']],
        ],

        'iq' => [
            ['baghdad',     33.3152, 44.3661, ['Багдад', 'Bag\'dod', 'Baghdad', '巴格达', 'Bağdat']],
            ['basra',       30.5085, 47.7804, ['Басра', 'Basra', 'Basra', '巴士拉', 'Basra']],
            ['erbil',       36.1911, 44.0091, ['Эрбиль', 'Erbil', 'Erbil', '埃尔比勒', 'Erbil']],
            ['mosul',       36.3350, 43.1189, ['Мосул', 'Mosul', 'Mosul', '摩苏尔', 'Musul']],
            ['sulaymaniyah', 35.5556, 45.4351, ['Сулеймания', 'Sulaymoniya', 'Sulaymaniyah', '苏莱曼尼亚', 'Süleymaniye']],
            ['kirkuk',      35.4681, 44.3922, ['Киркук', 'Kirkuk', 'Kirkuk', '基尔库克', 'Kerkük']],
            ['najaf',       31.9890, 44.3298, ['Наджаф', 'Najaf', 'Najaf', '纳杰夫', 'Necef']],
            ['karbala',     32.6160, 44.0242, ['Кербела', 'Karbalo', 'Karbala', '卡尔巴拉', 'Kerbela']],
        ],

        'jo' => [
            ['amman', 31.9539, 35.9106, ['Амман', 'Ammon', 'Amman', '安曼', 'Amman']],
            ['zarqa', 32.0728, 36.0880, ['Эз-Зарка', 'Zarqa', 'Zarqa', '扎尔卡', 'Zerka']],
            ['aqaba', 29.5321, 35.0063, ['Акаба', 'Aqaba', 'Aqaba', '亚喀巴', 'Akabe']],
            ['irbid', 32.5556, 35.8500, ['Ирбид', 'Irbid', 'Irbid', '伊尔比德', 'İrbid']],
            ['maan',  30.1962, 35.7340, ['Маан', 'Maan', 'Ma\'an', '马安', 'Maan']],
            ['madaba', 31.7157, 35.7938, ['Мадаба', 'Madaba', 'Madaba', '马达巴', 'Madaba']],
        ],

        'lb' => [
            ['beirut', 33.8938, 35.5018, ['Бейрут', 'Bayrut', 'Beirut', '贝鲁特', 'Beyrut']],
            ['tripoli', 34.4367, 35.8497, ['Триполи', 'Tripoli', 'Tripoli', '的黎波里', 'Trablusşam']],
            ['sidon',  33.5571, 35.3729, ['Сайда', 'Sayda', 'Sidon', '西顿', 'Sayda']],
            ['zahle',  33.8463, 35.9020, ['Захле', 'Zahla', 'Zahle', '扎赫勒', 'Zahle']],
            ['tyre',   33.2705, 35.1939, ['Тир', 'Sur', 'Tyre', '提尔', 'Sur']],
        ],

        'il' => [
            ['tel-aviv',   32.0853, 34.7818, ['Тель-Авив', 'Tel-Aviv', 'Tel Aviv', '特拉维夫', 'Tel Aviv']],
            ['jerusalem',  31.7683, 35.2137, ['Иерусалим', 'Quddus', 'Jerusalem', '耶路撒冷', 'Kudüs']],
            ['haifa',      32.7940, 34.9896, ['Хайфа', 'Xayfa', 'Haifa', '海法', 'Hayfa']],
            ['ashdod',     31.8044, 34.6553, ['Ашдод', 'Ashdod', 'Ashdod', '阿什杜德', 'Aşdod']],
            ['petah-tikva', 32.0878, 34.8878, ['Петах-Тиква', 'Petah-Tikva', 'Petah Tikva', '佩塔提克瓦', 'Petah Tikva']],
            ['netanya',    32.3215, 34.8532, ['Нетания', 'Netaniya', 'Netanya', '内坦亚', 'Netanya']],
            ['beer-sheva', 31.2530, 34.7915, ['Беэр-Шева', 'Beer-Sheva', 'Beer Sheva', '贝尔谢巴', 'Beer Şeva']],
        ],

        'eg' => [
            ['cairo',     30.0444, 31.2357, ['Каир', 'Qohira', 'Cairo', '开罗', 'Kahire']],
            ['alexandria', 31.2001, 29.9187, ['Александрия', 'Iskandariya', 'Alexandria', '亚历山大', 'İskenderiye']],
            ['giza',      30.0131, 31.2089, ['Гиза', 'Giza', 'Giza', '吉萨', 'Giza']],
            ['port-said', 31.2653, 32.3019, ['Порт-Саид', 'Port-Said', 'Port Said', '塞得港', 'Port Said']],
            ['suez',      29.9668, 32.5498, ['Суэц', 'Suvaysh', 'Suez', '苏伊士', 'Süveyş']],
            ['ismailia',  30.5965, 32.2715, ['Исмаилия', 'Ismoiliya', 'Ismailia', '伊斯梅利亚', 'İsmailiye']],
            ['damietta',  31.4165, 31.8133, ['Думьят', 'Dumyat', 'Damietta', '杜姆亚特', 'Dimyat']],
            ['mansoura',  31.0409, 31.3785, ['Эль-Мансура', 'Mansura', 'Mansoura', '曼苏拉', 'Mansura']],
            ['tanta',     30.7865, 31.0004, ['Танта', 'Tanta', 'Tanta', '坦塔', 'Tanta']],
            ['asyut',     27.1809, 31.1837, ['Асьют', 'Asyut', 'Asyut', '艾斯尤特', 'Asyut']],
            ['aswan',     24.0889, 32.8998, ['Асуан', 'Asvon', 'Aswan', '阿斯旺', 'Asvan']],
        ],

        'pl' => [
            ['warsaw',     52.2297, 21.0122, ['Варшава', 'Varshava', 'Warsaw', '华沙', 'Varşova']],
            ['krakow',     50.0647, 19.9450, ['Краков', 'Krakov', 'Krakow', '克拉科夫', 'Krakov']],
            ['wroclaw',    51.1079, 17.0385, ['Вроцлав', 'Vrotslav', 'Wroclaw', '弗罗茨瓦夫', 'Vroclav']],
            ['poznan',     52.4064, 16.9252, ['Познань', 'Poznan', 'Poznan', '波兹南', 'Poznan']],
            ['gdansk',     54.3520, 18.6466, ['Гданьск', 'Gdansk', 'Gdansk', '格但斯克', 'Gdansk']],
            ['lodz',       51.7592, 19.4560, ['Лодзь', 'Lodz', 'Lodz', '罗兹', 'Lodz']],
            ['katowice',   50.2649, 19.0238, ['Катовице', 'Katovitse', 'Katowice', '卡托维兹', 'Katowice']],
            ['szczecin',   53.4285, 14.5528, ['Щецин', 'Shchetsin', 'Szczecin', '什切青', 'Szczecin']],
            ['lublin',     51.2465, 22.5684, ['Люблин', 'Lyublin', 'Lublin', '卢布林', 'Lublin']],
            ['bialystok',  53.1325, 23.1688, ['Белосток', 'Belostok', 'Bialystok', '比亚韦斯托克', 'Bialystok']],
            ['bydgoszcz',  53.1235, 18.0084, ['Быдгощ', 'Bydgoshch', 'Bydgoszcz', '比得哥什', 'Bydgoszcz']],
            ['gdynia',     54.5189, 18.5305, ['Гдыня', 'Gdinya', 'Gdynia', '格丁尼亚', 'Gdynia']],
            ['czestochowa', 50.8118, 19.1203, ['Ченстохова', 'Chenstoxova', 'Czestochowa', '琴斯托霍瓦', 'Czestochowa']],
            ['rzeszow',    50.0413, 21.9990, ['Жешув', 'Jeshuv', 'Rzeszow', '热舒夫', 'Rzeszow']],
        ],

        'cz' => [
            ['prague',          50.0755, 14.4378, ['Прага', 'Praga', 'Prague', '布拉格', 'Prag']],
            ['brno',            49.1951, 16.6068, ['Брно', 'Brno', 'Brno', '布尔诺', 'Brno']],
            ['ostrava',         49.8209, 18.2625, ['Острава', 'Ostrava', 'Ostrava', '俄斯特拉发', 'Ostrava']],
            ['plzen',           49.7384, 13.3736, ['Пльзень', 'Plzen', 'Plzen', '比尔森', 'Plzen']],
            ['olomouc',         49.5938, 17.2509, ['Оломоуц', 'Olomouts', 'Olomouc', '奥洛穆茨', 'Olomouc']],
            ['liberec',         50.7663, 15.0543, ['Либерец', 'Liberets', 'Liberec', '利贝雷茨', 'Liberec']],
            ['hradec-kralove',  50.2093, 15.8328, ['Градец-Кралове', 'Gradets-Kralove', 'Hradec Kralove', '赫拉德茨-克拉洛韦', 'Hradec Kralove']],
            ['pardubice',       50.0343, 15.7812, ['Пардубице', 'Pardubitse', 'Pardubice', '帕尔杜比采', 'Pardubice']],
            ['usti-nad-labem',  50.6607, 14.0323, ['Усти-над-Лабем', 'Usti-nad-Labem', 'Usti nad Labem', '拉贝河畔乌斯季', 'Usti nad Labem']],
            ['ceske-budejovice', 48.9745, 14.4743, ['Ческе-Будеёвице', 'Cheske-Budeyovitse', 'Ceske Budejovice', '捷克布杰约维采', 'Ceske Budejovice']],
            ['zlin',            49.2265, 17.6706, ['Злин', 'Zlin', 'Zlin', '兹林', 'Zlin']],
        ],

        'sk' => [
            ['bratislava',     48.1486, 17.1077, ['Братислава', 'Bratislava', 'Bratislava', '布拉迪斯拉发', 'Bratislava']],
            ['kosice',         48.7164, 21.2611, ['Кошице', 'Koshitse', 'Kosice', '科希策', 'Kosice']],
            ['zilina',         49.2231, 18.7394, ['Жилина', 'Jilina', 'Zilina', '日利纳', 'Zilina']],
            ['nitra',          48.3069, 18.0864, ['Нитра', 'Nitra', 'Nitra', '尼特拉', 'Nitra']],
            ['trnava',         48.3774, 17.5872, ['Трнава', 'Trnava', 'Trnava', '特尔纳瓦', 'Trnava']],
            ['banska-bystrica', 48.7395, 19.1531, ['Банска-Бистрица', 'Banska-Bistritsa', 'Banska Bystrica', '班斯卡-比斯特里察', 'Banska Bystrica']],
            ['presov',         48.9985, 21.2339, ['Прешов', 'Preshov', 'Presov', '普雷绍夫', 'Presov']],
        ],

        'hu' => [
            ['budapest',   47.4979, 19.0402, ['Будапешт', 'Budapesht', 'Budapest', '布达佩斯', 'Budapeşte']],
            ['debrecen',   47.5316, 21.6273, ['Дебрецен', 'Debretsen', 'Debrecen', '德布勒森', 'Debrecen']],
            ['gyor',       47.6875, 17.6504, ['Дьёр', 'Dyor', 'Gyor', '杰尔', 'Györ']],
            ['szeged',     46.2530, 20.1414, ['Сегед', 'Seged', 'Szeged', '塞格德', 'Szeged']],
            ['miskolc',    48.1035, 20.7784, ['Мишкольц', 'Mishkolts', 'Miskolc', '米什科尔茨', 'Miskolc']],
            ['pecs',       46.0727, 18.2323, ['Печ', 'Pech', 'Pecs', '佩奇', 'Pecs']],
            ['kecskemet',  46.8964, 19.6897, ['Кечкемет', 'Kechkemet', 'Kecskemet', '凯奇凯梅特', 'Kecskemet']],
            ['nyiregyhaza', 47.9554, 21.7167, ['Ньиредьхаза', 'Nyiredyhaza', 'Nyiregyhaza', '尼赖吉哈佐', 'Nyiregyhaza']],
        ],

        'ro' => [
            ['bucharest',  44.4268, 26.1025, ['Бухарест', 'Buxarest', 'Bucharest', '布加勒斯特', 'Bükreş']],
            ['cluj-napoca', 46.7712, 23.6236, ['Клуж-Напока', 'Kluj-Napoka', 'Cluj-Napoca', '克卢日-纳波卡', 'Cluj-Napoca']],
            ['timisoara',  45.7489, 21.2087, ['Тимишоара', 'Timishoara', 'Timisoara', '蒂米什瓦拉', 'Timişoara']],
            ['constanta',  44.1598, 28.6348, ['Констанца', 'Konstantsa', 'Constanta', '康斯坦察', 'Köstence']],
            ['iasi',       47.1585, 27.6014, ['Яссы', 'Yassi', 'Iasi', '雅西', 'Yaş']],
            ['brasov',     45.6580, 25.6012, ['Брашов', 'Brashov', 'Brasov', '布拉索夫', 'Braşov']],
            ['craiova',    44.3302, 23.7949, ['Крайова', 'Krayova', 'Craiova', '克拉约瓦', 'Craiova']],
            ['galati',     45.4353, 28.0080, ['Галац', 'Galats', 'Galati', '加拉茨', 'Galati']],
            ['ploiesti',   44.9414, 26.0225, ['Плоешти', 'Ploeshti', 'Ploiesti', '普洛耶什蒂', 'Ploieşti']],
            ['oradea',     47.0465, 21.9189, ['Орадя', 'Oradya', 'Oradea', '奥拉迪亚', 'Oradea']],
            ['arad',       46.1866, 21.3123, ['Арад', 'Arad', 'Arad', '阿拉德', 'Arad']],
            ['sibiu',      45.7983, 24.1256, ['Сибиу', 'Sibiu', 'Sibiu', '锡比乌', 'Sibiu']],
        ],

        'bg' => [
            ['sofia',         42.6977, 23.3219, ['София', 'Sofiya', 'Sofia', '索非亚', 'Sofya']],
            ['plovdiv',       42.1354, 24.7453, ['Пловдив', 'Plovdiv', 'Plovdiv', '普罗夫迪夫', 'Filibe']],
            ['varna',         43.2141, 27.9147, ['Варна', 'Varna', 'Varna', '瓦尔纳', 'Varna']],
            ['burgas',        42.5048, 27.4626, ['Бургас', 'Burgas', 'Burgas', '布尔加斯', 'Burgaz']],
            ['ruse',          43.8356, 25.9657, ['Русе', 'Ruse', 'Ruse', '鲁塞', 'Rusçuk']],
            ['stara-zagora',  42.4258, 25.6345, ['Стара-Загора', 'Stara-Zagora', 'Stara Zagora', '旧扎戈拉', 'Eski Zağra']],
            ['pleven',        43.4170, 24.6067, ['Плевен', 'Pleven', 'Pleven', '普列文', 'Plevne']],
            ['veliko-tarnovo', 43.0757, 25.6172, ['Велико-Тырново', 'Veliko-Tirnovo', 'Veliko Tarnovo', '大特尔诺沃', 'Tırnova']],
            ['sliven',        42.6858, 26.3292, ['Сливен', 'Sliven', 'Sliven', '斯利文', 'Sliven']],
            ['shumen',        43.2712, 26.9361, ['Шумен', 'Shumen', 'Shumen', '舒门', 'Şumnu']],
        ],

        'rs' => [
            ['belgrade',  44.7866, 20.4489, ['Белград', 'Belgrad', 'Belgrade', '贝尔格莱德', 'Belgrad']],
            ['novi-sad',  45.2671, 19.8335, ['Нови-Сад', 'Novi-Sad', 'Novi Sad', '诺维萨德', 'Novi Sad']],
            ['nis',       43.3209, 21.8958, ['Ниш', 'Nish', 'Nis', '尼什', 'Niş']],
            ['kragujevac', 44.0128, 20.9114, ['Крагуевац', 'Kraguyevats', 'Kragujevac', '克拉古耶瓦茨', 'Kragujevac']],
            ['subotica',  46.1005, 19.6651, ['Суботица', 'Subotitsa', 'Subotica', '苏博蒂察', 'Subotica']],
            ['pancevo',   44.8708, 20.6403, ['Панчево', 'Panchevo', 'Pancevo', '潘切沃', 'Pançova']],
            ['smederevo', 44.6633, 20.9289, ['Смедерево', 'Smederevo', 'Smederevo', '斯梅代雷沃', 'Semendire']],
            ['zrenjanin', 45.3836, 20.3819, ['Зренянин', 'Zrenyanin', 'Zrenjanin', '兹雷尼亚宁', 'Zrenjanin']],
        ],

        'hr' => [
            ['zagreb',  45.8150, 15.9819, ['Загреб', 'Zagreb', 'Zagreb', '萨格勒布', 'Zagreb']],
            ['split',   43.5081, 16.4402, ['Сплит', 'Split', 'Split', '斯普利特', 'Split']],
            ['rijeka',  45.3271, 14.4422, ['Риека', 'Rieka', 'Rijeka', '里耶卡', 'Rijeka']],
            ['osijek',  45.5550, 18.6955, ['Осиек', 'Osiek', 'Osijek', '奥西耶克', 'Osijek']],
            ['zadar',   44.1194, 15.2314, ['Задар', 'Zadar', 'Zadar', '扎达尔', 'Zadar']],
            ['varazdin', 46.3057, 16.3366, ['Вараждин', 'Varajdin', 'Varazdin', '瓦拉日丁', 'Varaždin']],
            ['pula',    44.8666, 13.8496, ['Пула', 'Pula', 'Pula', '普拉', 'Pula']],
        ],

        'si' => [
            ['ljubljana', 46.0569, 14.5058, ['Любляна', 'Lyublyana', 'Ljubljana', '卢布尔雅那', 'Ljubljana']],
            ['maribor',   46.5547, 15.6459, ['Марибор', 'Maribor', 'Maribor', '马里博尔', 'Maribor']],
            ['koper',     45.5481, 13.7302, ['Копер', 'Koper', 'Koper', '科佩尔', 'Koper']],
            ['celje',     46.2309, 15.2604, ['Целе', 'Tsele', 'Celje', '采列', 'Celje']],
            ['kranj',     46.2389, 14.3556, ['Крань', 'Kranj', 'Kranj', '克拉尼', 'Kranj']],
            ['novo-mesto', 45.8010, 15.1710, ['Ново-Место', 'Novo-Mesto', 'Novo Mesto', '新梅斯托', 'Novo Mesto']],
        ],

        'ua' => [
            ['kyiv',           50.4501, 30.5234, ['Киев', 'Kiyev', 'Kyiv', '基辅', 'Kiev']],
            ['kharkiv',        49.9935, 36.2304, ['Харьков', 'Xarkov', 'Kharkiv', '哈尔科夫', 'Harkiv']],
            ['odesa',          46.4825, 30.7233, ['Одесса', 'Odessa', 'Odesa', '敖德萨', 'Odesa']],
            ['dnipro',         48.4647, 35.0462, ['Днепр', 'Dnepr', 'Dnipro', '第聂伯罗', 'Dnipro']],
            ['lviv',           49.8397, 24.0297, ['Львов', 'Lvov', 'Lviv', '利沃夫', 'Lviv']],
            ['zaporizhzhia',   47.8388, 35.1396, ['Запорожье', 'Zaporojye', 'Zaporizhzhia', '扎波罗热', 'Zaporijya']],
            ['kryvyi-rih',     47.9105, 33.3918, ['Кривой Рог', 'Krivoy Rog', 'Kryvyi Rih', '克里沃罗格', 'Kriviy Rih']],
            ['mykolaiv',       46.9750, 31.9946, ['Николаев', 'Nikolayev', 'Mykolaiv', '尼古拉耶夫', 'Mykolayiv']],
            ['kherson',        46.6354, 32.6169, ['Херсон', 'Xerson', 'Kherson', '赫尔松', 'Herson']],
            ['vinnytsia',      49.2331, 28.4682, ['Винница', 'Vinnitsa', 'Vinnytsia', '文尼察', 'Vinnitsya']],
            ['poltava',        49.5883, 34.5514, ['Полтава', 'Poltava', 'Poltava', '波尔塔瓦', 'Poltava']],
            ['kremenchuk',     49.0631, 33.4285, ['Кременчуг', 'Kremenchug', 'Kremenchuk', '克列缅丘格', 'Kremençuk']],
            ['cherkasy',       49.4444, 32.0598, ['Черкассы', 'Cherkassi', 'Cherkasy', '切尔卡瑟', 'Çerkası']],
            ['zhytomyr',       50.2547, 28.6587, ['Житомир', 'Jitomir', 'Zhytomyr', '日托米尔', 'Jitomir']],
            ['ivano-frankivsk', 48.9226, 24.7111, ['Ивано-Франковск', 'Ivano-Frankovsk', 'Ivano-Frankivsk', '伊万诺-弗兰科夫斯克', 'Ivano-Frankivsk']],
            ['ternopil',       49.5535, 25.5948, ['Тернополь', 'Ternopol', 'Ternopil', '捷尔诺波尔', 'Ternopil']],
            ['chernivtsi',     48.2921, 25.9358, ['Черновцы', 'Chernovtsi', 'Chernivtsi', '切尔诺夫策', 'Çernivtsi']],
            ['uzhhorod',       48.6208, 22.2879, ['Ужгород', 'Ujgorod', 'Uzhhorod', '乌日霍罗德', 'Ujhorod']],
        ],

        'md' => [
            ['chisinau', 47.0105, 28.8638, ['Кишинёв', 'Kishinyov', 'Chisinau', '基希讷乌', 'Kişinev']],
            ['balti',   47.7615, 27.9292, ['Бельцы', 'Beltsi', 'Balti', '伯尔兹', 'Bălți']],
            ['tiraspol', 46.8403, 29.6433, ['Тирасполь', 'Tiraspol', 'Tiraspol', '蒂拉斯波尔', 'Tiraspol']],
            ['cahul',   45.9075, 28.1944, ['Кагул', 'Kagul', 'Cahul', '卡胡尔', 'Cahul']],
        ],

        'lt' => [
            ['vilnius',  54.6872, 25.2797, ['Вильнюс', 'Vilnyus', 'Vilnius', '维尔纽斯', 'Vilnius']],
            ['kaunas',   54.8985, 23.9036, ['Каунас', 'Kaunas', 'Kaunas', '考纳斯', 'Kaunas']],
            ['klaipeda', 55.7033, 21.1443, ['Клайпеда', 'Klaypeda', 'Klaipeda', '克莱佩达', 'Klaipėda']],
            ['siauliai', 55.9333, 23.3167, ['Шяуляй', 'Shyaulyay', 'Siauliai', '希奥利艾', 'Šiauliai']],
            ['panevezys', 55.7333, 24.3500, ['Паневежис', 'Panevejis', 'Panevezys', '帕内韦日斯', 'Panevėžys']],
            ['alytus',   54.3963, 24.0458, ['Алитус', 'Alitus', 'Alytus', '阿利图斯', 'Alytus']],
        ],

        'lv' => [
            ['riga',      56.9496, 24.1052, ['Рига', 'Riga', 'Riga', '里加', 'Riga']],
            ['daugavpils', 55.8714, 26.5161, ['Даугавпилс', 'Daugavpils', 'Daugavpils', '陶格夫匹尔斯', 'Daugavpils']],
            ['liepaja',   56.5047, 21.0108, ['Лиепая', 'Liyepaya', 'Liepaja', '利耶帕亚', 'Liepāja']],
            ['ventspils', 57.3894, 21.5606, ['Вентспилс', 'Ventspils', 'Ventspils', '文茨皮尔斯', 'Ventspils']],
            ['jelgava',   56.6511, 23.7214, ['Елгава', 'Yelgava', 'Jelgava', '叶尔加瓦', 'Jelgava']],
            ['rezekne',   56.5100, 27.3319, ['Резекне', 'Rezekne', 'Rezekne', '雷泽克内', 'Rēzekne']],
        ],

        'ee' => [
            ['tallinn',     59.4370, 24.7536, ['Таллин', 'Tallin', 'Tallinn', '塔林', 'Tallinn']],
            ['tartu',       58.3780, 26.7290, ['Тарту', 'Tartu', 'Tartu', '塔尔图', 'Tartu']],
            ['narva',       59.3797, 28.1791, ['Нарва', 'Narva', 'Narva', '纳尔瓦', 'Narva']],
            ['parnu',       58.3859, 24.4971, ['Пярну', 'Pyarnu', 'Parnu', '派尔努', 'Pärnu']],
            ['kohtla-jarve', 59.3986, 27.2731, ['Кохтла-Ярве', 'Kohtla-Yarve', 'Kohtla-Jarve', '科赫特拉-耶尔韦', 'Kohtla-Järve']],
        ],
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
            array_sum(array_map(count(...), self::CITIES)),
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

        $this->cities($country, self::CITIES[$code] ?? []);
    }

    /**
     * Города страны.
     *
     * Ищутся по паре «страна + slug»: один и тот же slug в двух
     * странах — это два разных города, и искать город по одному
     * только slug значило бы связать сербский Ниш с турецким.
     *
     * @param  list<array{0: string, 1: float, 2: float, 3: list<string>}>  $rows
     */
    private function cities(Country $country, array $rows): void
    {
        foreach ($rows as $sort => [$slug, $lat, $lng, $names]) {
            $city = City::updateOrCreate(
                ['country_id' => $country->id, 'slug' => $slug],
                ['lat' => $lat, 'lng' => $lng, 'sort' => $sort, 'is_active' => true],
            );

            foreach (self::LOCALES as $i => $locale) {
                $city->translations()->updateOrCreate(['locale' => $locale], ['name' => $names[$i]]);
            }
        }
    }
}
