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
     * Ключ типа компании из вольной записи в таблице импорта.
     *
     * «trading» и «торговая» — это trader из справочника; неизвестное
     * значение остаётся как есть и всплывёт на карточке, а не потеряется.
     */
    public static function typeKey(?string $raw): ?string
    {
        $value = mb_strtolower(trim((string) $raw));

        if ($value === '') {
            return null;
        }

        return match ($value) {
            'trading', 'trade', 'торговая', 'торговая компания' => 'trader',
            'производитель' => 'manufacturer',
            'дистрибьютор' => 'distributor',
            'импортёр', 'импортер' => 'importer',
            'услуги', 'services' => 'service',
            default => $value,
        };
    }
}
