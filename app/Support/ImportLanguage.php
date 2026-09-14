<?php

declare(strict_types=1);

namespace App\Support;

use Illuminate\Support\Carbon;
use Throwable;

/**
 * Язык таблицы, которую менеджер загружает в админку.
 *
 * Файл готовит человек и на том языке, на котором работает: заголовок
 * столбца бывает «Категория», «Kategoriya» и «Category», сумма —
 * «250 000 000», «250 млн» и «1,000,000», дата — «30.10.2026» и
 * «30 октября 2026». Требовать единственно верное написание значит
 * заставлять переделывать файл, поэтому словари собраны здесь и
 * применяются до того, как значение попадёт в модель.
 *
 * Все сравнения идут по normalize(): регистр, «ё», неразрывные
 * пробелы из Excel, кавычки и четыре вида апострофов в узбекских
 * названиях приводятся к одному виду.
 */
final class ImportLanguage
{
    /**
     * Как называют столбец в таблице тендеров: имя столбца → синонимы.
     *
     * Словари у каждого импортёра свои: «Название» в тендерах — это
     * заголовок закупки, а в компаниях — название компании, и общий
     * список развёл бы их по разным столбцам.
     *
     * Списки заданы уже нормализованными — сравнивать их с заголовком
     * файла можно напрямую.
     *
     * @var array<string, list<string>>
     */
    public const TENDER_HEADERS = [
        'title' => ['заголовок', 'название', 'наименование', 'предмет закупки', 'предмет контракта', 'предмет',
            'наименование закупки', 'название закупки', 'тема', 'лот', 'тендер',
            'title', 'tender', 'tender title', 'tender name', 'name', 'subject', 'lot',
            'nomi', 'sarlavha', 'mavzu', 'başlık', 'konu', '标题', '名称'],

        'description' => ['описание', 'подробности', 'детали', 'текст', 'условия',
            'description', 'details', 'text', 'tavsif', 'izoh', 'batafsil', 'açıklama', 'detay', '描述', '说明'],

        'customer' => ['заказчик', 'заказчик закупки', 'организатор', 'организатор закупки', 'организация',
            'покупатель', 'клиент',
            'customer', 'client', 'buyer', 'procuring entity', 'issuer', 'organization', 'organisation',
            'buyurtmachi', 'tashkilot', 'mijoz', 'müşteri', 'kurum', '客户', '采购方'],

        'category_id' => ['категория', 'категории', 'категория товара', 'товарная группа', 'раздел', 'рубрика',
            'отрасль', 'сфера', 'группа', 'товар', 'продукция',
            'category', 'categories', 'section', 'industry', 'sector', 'group', 'product',
            'kategoriya', 'turkum', "bo'lim", 'soha', 'yonalish', 'kategori', 'bölüm', 'sektör', '类别', '分类'],

        'country_id' => ['страна', 'государство', 'country', 'state', 'mamlakat', 'davlat', 'ülke', '国家'],

        'location' => ['город', 'регион', 'область', 'место', 'адрес', 'местоположение',
            'city', 'region', 'location', 'address', 'place',
            'shahar', 'viloyat', 'manzil', 'joy', 'şehir', 'bölge', 'adres', '城市', '地区'],

        'budget' => ['бюджет', 'сумма', 'сумма контракта', 'стоимость', 'стоимость контракта', 'цена',
            'начальная цена', 'начальная (максимальная) цена', 'нмцк',
            'budget', 'amount', 'price', 'cost', 'sum', 'value', 'estimated value', 'contract value', 'tender value',
            'byudjet', 'summa', 'narx', 'qiymat', 'bütçe', 'tutar', 'fiyat', '预算', '金额'],

        'currency' => ['валюта', 'currency', 'valyuta', 'pul birligi', 'para birimi', '货币'],

        'deadline_at' => ['прием заявок до', 'срок подачи', 'срок', 'дедлайн', 'дата окончания', 'окончание приема',
            'дата окончания подачи', 'окончание подачи заявок', 'дата окончания приема заявок', 'дата закрытия', 'до',
            'deadline', 'submission deadline', 'bid deadline', 'due date', 'due', 'end date',
            'closing date', 'closing', 'last date', 'last date of submission',
            'muddat', 'oxirgi muddat', 'tugash sanasi', 'son muddat', 'bitiş tarihi', 'son tarih', '截止日期'],

        'source_url' => ['ссылка на источник', 'ссылка на тендер', 'ссылка', 'источник',
            'url', 'tender url', 'tender link', 'link', 'source',
            'havola', 'manba', 'bağlantı', 'kaynak', '链接', '来源'],

        'contact_name' => ['контактное лицо', 'контакт', 'фио', 'ответственный',
            'contact', 'contact person', 'aloqa shaxsi', 'masul shaxs', 'ilgili kişi', 'yetkili', '联系人'],

        'contact_phone' => ['телефон', 'тел', 'номер телефона',
            'phone', 'telephone', 'mobile', 'telefon', 'telefon raqami', 'raqam', '电话'],

        'contact_email' => ['почта', 'эл. почта', 'электронная почта', 'мейл',
            'email', 'e-mail', 'mail', 'pochta', 'elektron pochta', 'e-posta', 'eposta', '邮箱', '电子邮件'],

        'status' => ['опубликовать', 'публиковать', 'публикация', 'статус',
            'publish', 'published', 'status', 'nashr etish', 'holat', 'yayınla', 'durum', '状态', '发布'],
    ];

    /**
     * Как называют столбец в таблице компаний.
     *
     * @var array<string, list<string>>
     */
    public const COMPANY_HEADERS = [
        'tin' => ['инн', 'налоговый номер', 'стир', 'tin', 'inn', 'stir', 'tax id', 'tax number',
            'vergi no', 'vergi numarası', '税号'],

        'name' => ['название', 'наименование', 'компания', 'название компании', 'организация', 'фирма',
            'name', 'company', 'company name', 'firm',
            'nomi', 'kompaniya', 'kompaniya nomi', 'tashkilot', 'şirket', 'firma', 'unvan', '公司', '名称'],

        'legal_name' => ['юридическое название', 'юр. название', 'полное название', 'официальное название',
            'legal name', 'full name', 'official name',
            'yuridik nomi', 'rasmiy nomi', 'toliq nomi', 'resmi unvan', 'ticaret unvanı', '法定名称'],

        'type' => ['тип компании', 'тип', 'вид компании', 'вид деятельности', 'роль',
            'type', 'company type', 'kind', 'role',
            'turi', 'kompaniya turi', 'faoliyat turi', 'tür', 'şirket türü', '类型'],

        'address' => ['адрес', 'юридический адрес', 'фактический адрес', 'address', 'manzil', 'adres', '地址'],

        'phone' => ['телефон', 'тел', 'номер телефона', 'контактный телефон',
            'phone', 'telephone', 'mobile', 'telefon', 'telefon raqami', '电话'],

        'email' => ['почта', 'эл. почта', 'электронная почта', 'мейл',
            'email', 'e-mail', 'mail', 'pochta', 'elektron pochta', 'e-posta', 'eposta', '邮箱', '电子邮件'],

        'website' => ['сайт', 'веб-сайт', 'веб сайт', 'вебсайт', 'адрес сайта',
            'website', 'web site', 'site', 'url', 'web',
            'sayt', 'veb-sayt', 'web sitesi', 'internet sitesi', '网站'],

        'description' => ['описание', 'о компании', 'деятельность', 'чем занимается',
            'description', 'about', 'activity', 'tavsif', 'faoliyat', 'açıklama', 'hakkında', '描述'],

        'founded_year' => ['год основания', 'основана', 'основан', 'год',
            'founded', 'founded year', 'year', 'established',
            'tashkil etilgan yil', 'tashkil topgan yil', 'yil', 'kuruluş yılı', '成立年份'],

        'employees_range' => ['сотрудников', 'количество сотрудников', 'численность', 'штат', 'персонал',
            'employees', 'staff', 'headcount', 'employees count',
            'xodimlar', 'xodimlar soni', 'çalışan sayısı', 'personel', '员工'],
    ];

    /** Код валюты → как её пишут словами и знаками. */
    private const CURRENCIES = [
        'UZS' => ['uzs', 'сум', 'сумы', 'сумов', 'сумм', 'сўм', "so'm", 'som', 'soum'],
        'USD' => ['usd', '$', 'доллар', 'доллары', 'долларов', 'долл', 'дол', 'dollar', 'dollars', 'dolar', '美元'],
        'EUR' => ['eur', '€', 'евро', 'euro', 'avro', '欧元'],
        'RUB' => ['rub', '₽', 'руб', 'рубль', 'рубли', 'рублей', 'ruble', 'rubl', '卢布'],
        'CNY' => ['cny', '¥', 'юань', 'юани', 'юаней', 'yuan', 'rmb', '元', '人民币'],
        'KZT' => ['kzt', '₸', 'тенге', 'tenge'],
    ];

    /** Утвердительный ответ в колонке «Опубликовать». */
    private const YES = ['да', 'д', 'yes', 'y', 'true', '1', '+', 'ok', 'on',
        'ha', 'xa', 'bor', 'опубликовать', 'публиковать', 'опубликован',
        'publish', 'published', 'active', 'evet', 'var', '是', '发布'];

    /**
     * Номер месяца → начала его названий. Сравнение по началу слова:
     * «октября», «октябрь» и «oktabr» — один и тот же месяц.
     *
     * @var array<int, list<string>>
     */
    private const MONTHS = [
        1 => ['январ', 'yanvar', 'january', 'jan', 'ocak'],
        2 => ['феврал', 'fevral', 'february', 'feb', 'şubat', 'subat'],
        3 => ['март', 'mart', 'march', 'mar'],
        4 => ['апрел', 'aprel', 'april', 'apr', 'nisan'],
        5 => ['май', 'мая', 'мае', 'may', 'mayıs'],
        6 => ['июн', 'iyun', 'june', 'jun', 'haziran'],
        7 => ['июл', 'iyul', 'july', 'jul', 'temmuz'],
        8 => ['август', 'avgust', 'august', 'aug', 'ağustos', 'agustos'],
        9 => ['сентябр', 'sentabr', 'sentyabr', 'september', 'sept', 'sep', 'eylül'],
        10 => ['октябр', 'oktabr', 'oktyabr', 'october', 'oct', 'ekim'],
        11 => ['ноябр', 'noyabr', 'november', 'nov', 'kasım', 'kasim'],
        12 => ['декабр', 'dekabr', 'december', 'dec', 'aralık', 'aralik'],
    ];

    /** «250 млн» — это 250 000 000, а не 250. */
    private const MULTIPLIERS = [
        1_000_000_000 => ['млрд', 'миллиард', 'mlrd', 'milliard', 'billion'],
        1_000_000 => ['млн', 'миллион', 'mln', 'million'],
        1_000 => ['тыс', 'тысяч', 'ming', 'thousand'],
    ];

    /** Написание, набранное человеком, — к единому виду. */
    public static function normalize(?string $value): string
    {
        $value = str_replace(
            ["\u{FEFF}", "\u{00A0}", "\u{202F}", "\u{2007}", "\u{200B}", 'ё', '«', '»', '"', '’', '‘', 'ʼ', 'ʻ', '`', '´'],
            ['', ' ', ' ', ' ', '', 'е', '', '', '', "'", "'", "'", "'", "'", "'"],
            mb_strtolower((string) $value),
        );

        return trim((string) preg_replace('/\s+/u', ' ', $value));
    }

    /**
     * Заголовок из файла — один из синонимов столбца?
     *
     * @param  list<string>  $aliases
     */
    public static function matches(string $header, array $aliases): bool
    {
        return in_array(self::normalize($header), $aliases, true);
    }

    /**
     * Код валюты. Незнакомое значение возвращается как есть — пусть
     * его отклонит валидация столбца, а не тихо подменит «UZS».
     */
    public static function currency(?string $state): string
    {
        $needle = self::normalize($state);

        if ($needle === '') {
            return 'UZS';
        }

        foreach (self::CURRENCIES as $code => $aliases) {
            if (in_array($needle, $aliases, true)) {
                return $code;
            }
        }

        return mb_strtoupper($needle);
    }

    public static function isYes(?string $state): bool
    {
        return in_array(self::normalize($state), self::YES, true);
    }

    /** «250 000 000», «1,000,000», «250 млн сум» — одно число. */
    public static function amount(?string $state): ?float
    {
        $raw = self::normalize($state);
        $multiplier = 1;

        // Множитель ищем до разбора диапазона: в «от 100 до 200 млн»
        // «млн» относится к обеим границам

        foreach (self::MULTIPLIERS as $value => $words) {
            foreach ($words as $word) {
                if (str_contains($raw, $word)) {
                    $multiplier = $value;

                    break 2;
                }
            }
        }

        $digits = self::digits(self::lowerBound($raw));

        return $digits === null ? null : $digits * $multiplier;
    }

    /**
     * Нижняя граница диапазона: «от 100 000 до 200 000» и
     * «100 000 — 200 000» дают 100 000.
     *
     * Без этого цифры обеих границ слипались в одно число, и вместо
     * ста тысяч в бюджет попадало сто миллиардов.
     */
    private static function lowerBound(string $value): string
    {
        $parts = preg_split('/\s*(?:—|–|-|\.{2,}|…|(?<!\p{L})(?:до|to)(?!\p{L}))\s*/u', $value) ?: [];

        foreach ($parts as $part) {
            if (preg_match('/\d/', $part) === 1) {
                return $part;
            }
        }

        return $value;
    }

    /**
     * Дата в формат базы: «30.10.2026», ISO, «30/10/2026»,
     * «30 октября 2026» и узбекское «2026 yil 30 oktabr».
     */
    public static function date(?string $state): ?string
    {
        $raw = trim((string) $state);

        if ($raw === '') {
            return null;
        }

        $raw = self::spellOutDate($raw) ?? $raw;

        foreach (['d.m.Y H:i', 'd.m.Y', 'Y-m-d H:i', 'Y-m-d', 'd/m/Y', 'd-m-Y', 'm/d/Y'] as $format) {
            try {
                $date = Carbon::createFromFormat($format, $raw);
            } catch (Throwable) {
                continue;
            }

            // «10/30/2026» как d/m/Y даёт 30-й месяц, а PHP молча
            // переносит его на 2028 год — такой разбор не считается
            $errors = Carbon::getLastErrors();

            if (is_array($errors) && ($errors['error_count'] + $errors['warning_count']) > 0) {
                continue;
            }

            if ($date !== null) {
                // Без времени — конец дня: «до 30 октября» включает 30-е
                if (! str_contains($format, 'H')) {
                    $date->endOfDay();
                }

                return $date->toDateTimeString();
            }
        }

        return $raw;
    }

    /** Дата с названием месяца → «30.10.2026». */
    private static function spellOutDate(string $value): ?string
    {
        $needle = self::normalize($value);
        $month = null;

        foreach (self::MONTHS as $number => $names) {
            foreach (explode(' ', $needle) as $word) {
                foreach ($names as $name) {
                    if (str_starts_with($word, $name)) {
                        $month = $number;

                        break 3;
                    }
                }
            }
        }

        if ($month === null) {
            return null;
        }

        preg_match_all('/\d+/u', $needle, $matches);

        $day = null;
        $year = null;

        // Порядок частей разный: «30 октября 2026» и «2026 yil 30 oktabr»
        foreach (array_map(intval(...), $matches[0]) as $number) {
            if ($number > 31) {
                $year ??= $number;
            } else {
                $day ??= $number;
            }
        }

        if ($day === null || $year === null) {
            return null;
        }

        return sprintf('%02d.%02d.%04d', $day, $month, $year);
    }

    /**
     * Число из строки. Разделители в файлах разные: «250 000 000,50»
     * и «250,000,000.50» — три цифры после последнего разделителя
     * означают тысячи, одна-две — копейки.
     */
    private static function digits(string $value): ?float
    {
        $digits = (string) preg_replace('/[^\d,.]/u', '', $value);

        if ($digits === '' || preg_match('/\d/', $digits) !== 1) {
            return null;
        }

        $separator = max(strrpos($digits, ',') ?: -1, strrpos($digits, '.') ?: -1);
        $tail = $separator > 0 ? substr($digits, $separator + 1) : '';

        $digits = $tail !== '' && strlen($tail) !== 3
            ? str_replace(',', '.', preg_replace('/[,.](?=[^,.]*[,.])/u', '', $digits) ?? $digits)
            : str_replace([',', '.'], '', $digits);

        return is_numeric($digits) ? (float) $digits : null;
    }
}
