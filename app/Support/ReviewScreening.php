<?php

declare(strict_types=1);

namespace App\Support;

/**
 * Автоматическая проверка отзыва перед публикацией.
 *
 * Не цензура и не оценка содержания: отрицательный отзыв площадке
 * нужен не меньше положительного. Ищутся ровно две вещи, из-за
 * которых текст нельзя пускать на витрину не глядя.
 *
 * Первая — контакты в тексте. Отзыв виден всем и бесплатно, а контакты
 * на площадке продаются: поставщик, вписавший свой телефон в отзыв,
 * раздаёт то, за что другие платят кредитами. Это не грубость,
 * а обход монетизации, и ловить его надо всегда.
 *
 * Вторая — брань. Публичная витрина с матом отпугивает покупателя
 * быстрее, чем один плохой отзыв.
 */
class ReviewScreening
{
    /**
     * Корни бранных слов.
     *
     * Именно корни, а не слова целиком: приставки и окончания
     * в русском меняют слово до неузнаваемости для точного списка.
     * Список намеренно короткий — задача не отфильтровать всё,
     * а отправить сомнительное человеку.
     */
    private const PROFANITY = [
        'хуй', 'хуе', 'хуё', 'пизд', 'ебал', 'ебан', 'ебат', 'ёбан', 'бляд',
        'муда', 'сука', 'гандон', 'долбоёб', 'долбоеб', 'пидор', 'пидар',
    ];

    /**
     * Причины, по которым отзыв уходит модератору. Пустой список —
     * можно публиковать.
     *
     * @return list<string>
     */
    public static function reasons(string $text): array
    {
        $reasons = [];
        $normalized = self::normalize($text);

        if (self::hasContacts($text)) {
            $reasons[] = 'В тексте есть контакты: телефон, почта или ссылка';
        }

        if (self::hasProfanity($normalized)) {
            $reasons[] = 'В тексте есть брань';
        }

        if (self::isShouting($text)) {
            $reasons[] = 'Текст набран заглавными буквами';
        }

        return $reasons;
    }

    /**
     * Приведение к виду, в котором обход подстановкой символов
     * не работает: «с-у-к-а» и «с у к а» становятся одним словом.
     */
    private static function normalize(string $text): string
    {
        $lower = mb_strtolower($text);

        // Латиница, похожая на кириллицу: «cyka» пишут именно так
        $lower = strtr($lower, [
            'a' => 'а', 'e' => 'е', 'o' => 'о', 'p' => 'р', 'c' => 'с',
            'y' => 'у', 'x' => 'х', 'k' => 'к', 'm' => 'м', 'b' => 'б',
        ]);

        return (string) preg_replace('/[^\p{L}\p{N}]+/u', '', $lower);
    }

    private static function hasProfanity(string $normalized): bool
    {
        foreach (self::PROFANITY as $root) {
            if (str_contains($normalized, $root)) {
                return true;
            }
        }

        return false;
    }

    /** Почта, ссылка или телефон в тексте. */
    private static function hasContacts(string $text): bool
    {
        if (preg_match('/[\w.+-]+@[\w-]+\.[a-z]{2,}/iu', $text) === 1) {
            return true;
        }

        if (preg_match('#(https?://|www\.|t\.me/|@[a-z0-9_]{4,})#iu', $text) === 1) {
            return true;
        }

        return self::hasPhone($text);
    }

    /**
     * Телефон в тексте.
     *
     * Отличить его от прочих чисел важнее, чем поймать любое: отзыв
     * с «ГОСТ 34028-2016» или «партия 12 000 000 сум» — это как раз
     * подробный полезный отзыв, и гонять его через модератора значит
     * наказывать за подробность.
     *
     * Телефоном считается одно из трёх:
     * — плюс и следом семь и более цифр: «+998 90 123-45-67»;
     * — девять и более цифр подряд без разделителей: «998901234567»;
     * — четыре и более групп цифр: «90 123 45 67».
     *
     * Номер стандарта — две группы, цена в миллионах — три; ни то,
     * ни другое под правило не попадает.
     */
    private static function hasPhone(string $text): bool
    {
        if (preg_match('/\+\s*(?:\d[\s()-]*){7,}/u', $text) === 1) {
            return true;
        }

        if (preg_match('/\d{9,}/u', $text) === 1) {
            return true;
        }

        return preg_match('/\d+(?:[\s()-]+\d+){3,}/u', $text) === 1;
    }

    /** Крик заглавными: раздражает читателя и обычно означает эмоции. */
    private static function isShouting(string $text): bool
    {
        $letters = (string) preg_replace('/[^\p{L}]+/u', '', $text);

        if (mb_strlen($letters) < 20) {
            return false;
        }

        $upper = (string) preg_replace('/[^\p{Lu}]+/u', '', $letters);

        return mb_strlen($upper) / mb_strlen($letters) > 0.7;
    }
}
