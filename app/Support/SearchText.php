<?php

declare(strict_types=1);

namespace App\Support;

/**
 * Нормализация текста для поиска: кириллица и латиница вперемешку.
 *
 * Узбекоязычная аудитория набирает на латинице — «sement», «armatura»,
 * «gisht», — а объявления чаще написаны кириллицей. Прямой LIKE давал
 * пустую выдачу на любой латинский запрос (аудит 29.08.2026, п. 5.4).
 *
 * Решение — хранить в search_text текст сразу в обеих графиках:
 * исходная форма плюс транслитерация в другую. Запрос при этом
 * не переводится (нормализуется регистр и узбекские апострофы) —
 * какую графику ни набери, одна из сохранённых форм совпадёт.
 */
class SearchText
{
    /** Кириллица → узбекская латиница. Многобуквенные — первыми. */
    private const CYR_TO_LAT = [
        'ё' => 'yo', 'ю' => 'yu', 'я' => 'ya', 'ч' => 'ch', 'ш' => 'sh', 'щ' => 'sh',
        'ж' => 'j', 'ц' => 's', 'э' => 'e', 'ъ' => '', 'ь' => '',
        'а' => 'a', 'б' => 'b', 'в' => 'v', 'г' => 'g', 'д' => 'd', 'е' => 'e',
        'з' => 'z', 'и' => 'i', 'й' => 'y', 'к' => 'k', 'л' => 'l', 'м' => 'm',
        'н' => 'n', 'о' => 'o', 'п' => 'p', 'р' => 'r', 'с' => 's', 'т' => 't',
        'у' => 'u', 'ф' => 'f', 'х' => 'x', 'ў' => 'o', 'қ' => 'q', 'ғ' => 'g', 'ҳ' => 'h',
    ];

    /** Латиница → кириллица. Диграфы — первыми, иначе «sh» станет «сх». */
    private const LAT_TO_CYR = [
        'yo' => 'ё', 'yu' => 'ю', 'ya' => 'я', 'ch' => 'ч', 'sh' => 'ш', 'ts' => 'ц', 'kh' => 'х',
        'a' => 'а', 'b' => 'б', 'c' => 'к', 'd' => 'д', 'e' => 'е', 'f' => 'ф',
        'g' => 'г', 'h' => 'х', 'i' => 'и', 'j' => 'ж', 'k' => 'к', 'l' => 'л',
        'm' => 'м', 'n' => 'н', 'o' => 'о', 'p' => 'п', 'q' => 'к', 'r' => 'р',
        's' => 'с', 't' => 'т', 'u' => 'у', 'v' => 'в', 'w' => 'в', 'x' => 'х',
        'y' => 'й', 'z' => 'з',
    ];

    /**
     * Нижний регистр, без узбекских апострофов, с одиночными пробелами.
     * «G'isht», «gʻisht» и «gisht» становятся одной строкой.
     */
    public static function normalize(string $text): string
    {
        $text = mb_strtolower(trim($text));
        $text = str_replace(["'", '’', '‘', 'ʻ', 'ʼ', '`'], '', $text);

        return (string) preg_replace('/\s+/u', ' ', $text);
    }

    /** Строка для колонки search_text: обе графики разом. */
    public static function index(string $text): string
    {
        $normalized = self::normalize($text);

        $forms = array_unique([
            $normalized,
            strtr($normalized, self::CYR_TO_LAT),
            strtr($normalized, self::LAT_TO_CYR),
        ]);

        return implode(' ', $forms);
    }

    /**
     * Варианты запроса для поиска по колонкам без индексной формы
     * (например, названия компаний): как набрано плюс транслитерации.
     *
     * @return list<string>
     */
    public static function variants(string $term): array
    {
        $normalized = self::normalize($term);

        return array_values(array_filter(array_unique([
            $normalized,
            strtr($normalized, self::CYR_TO_LAT),
            strtr($normalized, self::LAT_TO_CYR),
        ]), fn (string $v): bool => $v !== ''));
    }
}
