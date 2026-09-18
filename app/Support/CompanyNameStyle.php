<?php

declare(strict_types=1);

namespace App\Support;

/**
 * Приведение названий и типов компаний из внешних источников.
 *
 * Госреестр отдаёт названия целиком заглавными — «TOSHKENT MATRAS
 * LYUKS» на витрине выглядит криком. Название, написанное капсом,
 * переводится в «Каждое Слово С Заглавной»; названия со смешанным
 * регистром не трогаются — так их написал сам владелец.
 */
class CompanyNameStyle
{
    /** Юридические аббревиатуры, которым капс положен. */
    private const KEEP_UPPER = ['ООО', 'OOO', 'СП', 'ИП', 'УП', 'АЖ', 'МЧЖ', 'MCHJ', 'QMJ', 'XK', 'ХК', 'JV', 'LLC'];

    public static function humanize(string $name): string
    {
        $trimmed = trim($name);

        if ($trimmed === ''
            || $trimmed !== mb_strtoupper($trimmed)
            || preg_match('/\p{L}/u', $trimmed) !== 1) {
            return $trimmed;
        }

        $title = mb_convert_case(mb_strtolower($trimmed), MB_CASE_TITLE, 'UTF-8');

        $words = array_map(
            fn (string $w): string => in_array(mb_strtoupper($w), self::KEEP_UPPER, true)
                ? mb_strtoupper($w)
                : $w,
            explode(' ', $title),
        );

        return implode(' ', $words);
    }

    /**
     * Корни, по которым узнаётся тип компании, на пяти языках.
     *
     * Порядок важен: «производство и экспорт» — это производитель,
     * который ещё и вывозит, а не торговый дом, поэтому производство
     * проверяется раньше торговли.
     *
     * @var array<string, list<string>>
     */
    private const TYPE_STEMS = [
        'manufacturer' => ['производ', 'изготов', 'завод', 'фабрик', 'manufact', 'factory', 'producer',
            'ishlab chiqar', 'üretim', 'üretici', 'imalat', '制造', '生产'],
        'distributor' => ['дистриб', 'distrib', 'дилер', 'dealer', 'bayi', '经销'],
        'importer' => ['импорт', 'import', 'ithalat', '进口'],
        'trader' => ['торгов', 'экспорт', 'trade', 'trading', 'export', 'savdo', 'eksport',
            'ticaret', 'ihracat', '贸易', '出口'],
        'service' => ['услуг', 'сервис', 'service', 'xizmat', 'hizmet', '服务'],
    ];

    /**
     * Ключ типа компании из вольной записи в таблице импорта.
     *
     * Справочник знает пять типов, а в таблице пишут как придётся:
     * «производство», «Производство и экспорт», «üretim», «IT».
     * Поэтому узнаём не точное слово, а корень: «производ» — это
     * manufacturer на любом языке и в любом падеже.
     *
     * Совсем незнакомое значение остаётся как есть: оно всплывёт
     * на карточке и в админке, а не потеряется.
     */
    public static function typeKey(?string $raw): ?string
    {
        $value = mb_strtolower(trim((string) $raw));

        if ($value === '') {
            return null;
        }

        // Точные значения — первыми: «it» коротко и внутри слов
        // встречается слишком часто, чтобы искать его корнем
        $exact = match ($value) {
            'it', 'ит', 'айти', 'it-услуги', 'it services' => 'service',
            default => null,
        };

        if ($exact !== null) {
            return $exact;
        }

        foreach (self::TYPE_STEMS as $code => $stems) {
            foreach ($stems as $stem) {
                if (str_contains($value, $stem)) {
                    return $code;
                }
            }
        }

        return $value;
    }
}
