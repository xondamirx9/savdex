<?php

declare(strict_types=1);

namespace App\Support;

/**
 * Значение одной ячейки таблицы, набранной руками.
 *
 * Файл для загрузки готовит человек в Excel, а не выгружает система,
 * и в нём живут три привычки, на которых спотыкалась проверка полей:
 *
 * — прочерк вместо пустоты: «—», «-», «н/д», «не указан»;
 * — несколько значений в одной ячейке через косую черту:
 *   «info@a.com / sales@a.com», «+998 71 200-00-00 / +998 90 100-00-00»;
 * — пояснение рядом со значением: «около 6500 (по публичным данным)».
 *
 * Раньше такая строка не импортировалась целиком: компания терялась
 * из-за второго адреса почты, который никому не был нужен. Здесь
 * ячейка приводится к тому, что можно положить в колонку, а лишнее
 * отбрасывается — но только лишнее.
 */
final class ImportCell
{
    /** Как в таблицах пишут «данных нет». */
    private const BLANKS = [
        '-', '--', '---', '—', '–', '−', '.', '?', 'n/a', 'na', 'n.a.', 'none', 'null', 'unknown',
        'нет', 'нет данных', 'не указан', 'не указано', 'неизвестно', 'отсутствует',
        "yo'q", 'yoq', 'malumot yoq', 'bilinmiyor', 'yok', '无', '没有',
    ];

    /**
     * Чем в одной ячейке разделяют несколько значений.
     *
     * Косая черта — только отдельным словом, с пробелами по бокам:
     * без этого «https://site.com» разрезалось на «https:», и сайт
     * компании превращался в мусор.
     */
    private const SEPARATOR_PATTERN = '/\s*[;|,]\s*|\s+\/\s+|\R/u';

    /**
     * Текст ячейки: без пробелов по краям и без прочерков.
     *
     * @param  int|null  $max  длина колонки в базе; длиннее — обрезается
     *                         по границе слова, иначе строка не сохранится
     */
    public static function text(?string $value, ?int $max = null): ?string
    {
        $text = trim((string) preg_replace('/\s+/u', ' ', str_replace("\u{00A0}", ' ', (string) $value)));

        if ($text === '' || in_array(ImportLanguage::normalize($text), self::BLANKS, true)) {
            return null;
        }

        if ($max !== null && mb_strlen($text) > $max) {
            $cut = mb_substr($text, 0, $max);
            $space = mb_strrpos($cut, ' ');

            // Обрезаем по слову, но только если так остаётся
            // больше половины: «ООО» вместо названия — не данные
            $text = $space !== false && $space > $max / 2 ? mb_substr($cut, 0, $space) : $cut;
            $text = rtrim($text, ' ,.;/-');
        }

        return $text === '' ? null : $text;
    }

    /**
     * Первое из нескольких значений ячейки.
     *
     * Второй телефон и третья почта пропадают намеренно: колонка
     * в базе одна, а строку с «/» не примет ни проверка почты,
     * ни пользователь, который попробует по ней позвонить.
     */
    public static function first(?string $value, ?int $max = null): ?string
    {
        $text = self::text($value);

        if ($text === null) {
            return null;
        }

        $parts = preg_split(self::SEPARATOR_PATTERN, $text) ?: [];

        foreach ($parts as $part) {
            $part = self::text($part, $max);

            if ($part !== null) {
                return $part;
            }
        }

        return null;
    }

    /** Первый адрес почты из ячейки; мусор и прочерк — null. */
    public static function email(?string $value, int $max = 190): ?string
    {
        $text = self::text($value);

        if ($text === null) {
            return null;
        }

        // Почта не содержит ни косой черты, ни пробелов, поэтому
        // здесь режем по всему сразу — лишнего не разорвём
        foreach (preg_split('/[\s\/;|,]+/u', $text) ?: [] as $part) {
            $part = trim($part, " <>()[]\"'");

            if (filter_var($part, FILTER_VALIDATE_EMAIL) !== false && mb_strlen($part) <= $max) {
                return mb_strtolower($part);
            }
        }

        return null;
    }

    /**
     * Первый телефон из ячейки.
     *
     * Номер, который не помещается в колонку, отбрасывается целиком:
     * обрезанный телефон выглядит настоящим, но не звонит.
     */
    public static function phone(?string $value, int $max = 32): ?string
    {
        $phone = self::first($value);

        return $phone !== null && mb_strlen($phone) <= $max ? $phone : null;
    }

    /**
     * Год из ячейки: «1827 / 2003» — 1827, «осн. 1998 г.» — 1998.
     *
     * Нижняя граница — 1500: компании 1790 года основания существуют,
     * и отказывать им в загрузке из-за круглой даты незачем.
     */
    public static function year(?string $value): ?int
    {
        $text = self::text($value);

        if ($text === null || preg_match_all('/\d{4}/u', $text, $matches) === 0) {
            return null;
        }

        foreach ($matches[0] as $candidate) {
            $year = (int) $candidate;

            if ($year >= 1500 && $year <= (int) date('Y')) {
                return $year;
            }
        }

        return null;
    }

    /**
     * Численность в том виде, в каком её показывает карточка:
     * «50-100», «1000+», «6500».
     *
     * Из «около 6500 (по публичным данным)» остаётся число: колонка
     * короткая, а пояснение про публичные данные на витрине не нужно.
     */
    public static function employees(?string $value, int $max = 16): ?string
    {
        $text = self::text($value);

        if ($text === null) {
            return null;
        }

        $digits = str_replace(["\u{202F}", ' '], '', $text);

        if (preg_match('/\d+\s*[-–—]\s*\d+\+?|\d+\+|\d+/u', $digits, $found) === 1) {
            $range = str_replace(['–', '—'], '-', $found[0]);

            if (mb_strlen($range) <= $max) {
                return $range;
            }
        }

        return self::text($text, $max);
    }
}
