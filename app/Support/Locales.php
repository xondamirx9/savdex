<?php

declare(strict_types=1);

namespace App\Support;

/**
 * Языки площадки и адреса под них.
 *
 * Язык — часть адреса, а не состояние сессии. Раньше все пять языков
 * жили на одном адресе, и это ломало сразу несколько вещей:
 *
 * — поисковик видел одну страницу вместо пяти и индексировал ту,
 *   которую отдали роботу первой. Узбекоязычный запрос не находил
 *   ничего, хотя перевод существовал;
 * — ссылку нельзя было переслать: получатель открывал её на своём
 *   языке, а не на том, который отправитель имел в виду;
 * — hreflang проставить было не к чему — все языки указывали бы
 *   на один и тот же адрес, а это поисковик считает ошибкой.
 *
 * Русский живёт без префикса: это язык основной аудитории, и «/ru/»
 * в адресе главной страницы — лишний сегмент для большинства.
 * Остальные языки получают свой: /uz/catalog, /en/catalog.
 */
final class Locales
{
    /** Язык без префикса в адресе. */
    public const DEFAULT = 'ru';

    /**
     * Список языков в порядке показа в переключателе.
     *
     * hreflang отличается от кода там, где язык записывается разными
     * системами письма: китайский нужно указывать как zh-Hans —
     * поисковик иначе не знает, упрощённое это письмо или традиционное.
     *
     * @var array<string, array{label: string, short: string, hreflang: string}>
     */
    public const ALL = [
        'ru' => ['label' => 'Русский', 'short' => 'RU', 'hreflang' => 'ru'],
        'uz' => ['label' => 'O‘zbekcha', 'short' => 'UZ', 'hreflang' => 'uz'],
        'en' => ['label' => 'English', 'short' => 'EN', 'hreflang' => 'en'],
        'zh' => ['label' => '中文', 'short' => 'ZH', 'hreflang' => 'zh-Hans'],
        'tr' => ['label' => 'Türkçe', 'short' => 'TR', 'hreflang' => 'tr'],
    ];

    /** @return list<string> */
    public static function codes(): array
    {
        return array_keys(self::ALL);
    }

    /** Языки, у которых в адресе есть префикс. */
    public static function prefixed(): array
    {
        return array_values(array_diff(self::codes(), [self::DEFAULT]));
    }

    public static function supports(?string $locale): bool
    {
        return $locale !== null && array_key_exists($locale, self::ALL);
    }

    /** Префикс адреса: пустой для русского, «/uz» для остальных. */
    public static function prefix(string $locale): string
    {
        return $locale === self::DEFAULT ? '' : '/'.$locale;
    }

    /**
     * Отделить язык от пути.
     *
     * «/uz/catalog» → ['uz', '/catalog'], «/catalog» → [null, '/catalog'].
     * Отдельно разбирается «/uz» без хвоста — это главная страница,
     * и путь должен получиться «/», а не пустая строка.
     *
     * @return array{0: string|null, 1: string}
     */
    public static function split(string $path): array
    {
        $path = '/'.ltrim($path, '/');

        foreach (self::prefixed() as $code) {
            if ($path === '/'.$code) {
                return [$code, '/'];
            }

            if (str_starts_with($path, '/'.$code.'/')) {
                return [$code, substr($path, strlen($code) + 1)];
            }
        }

        return [null, $path];
    }

    /**
     * Адрес для переключателя языка.
     *
     * Для языков с префиксом — обычный адрес страницы. Русская ссылка
     * несёт явный маркер ?hl=ru: адрес без префикса сам по себе значит
     * «язык не указан», и сохранённый выбор (см. SetLocale) возвращал
     * бы человека обратно — переключиться на русский было бы нельзя.
     * SetLocale запоминает маркер и снимает его редиректом.
     */
    public static function switchUrl(string $path, string $locale): string
    {
        $url = self::url($path, $locale);

        if ($locale !== self::DEFAULT) {
            return $url;
        }

        return $url.(str_contains($url, '?') ? '&' : '?').'hl='.self::DEFAULT;
    }

    /**
     * Адрес пути на заданном языке — полный, с доменом.
     *
     * Путь принимается в любом виде: уже с чужим префиксом языка,
     * без него, с параметрами запроса. Чужой префикс снимается,
     * иначе при переключении языка адреса склеивались бы в «/uz/en/».
     */
    public static function url(string $path, ?string $locale = null): string
    {
        $locale ??= app()->getLocale();

        $query = '';
        if (($pos = strpos($path, '?')) !== false) {
            $query = substr($path, $pos);
            $path = substr($path, 0, $pos);
        }

        [, $clean] = self::split($path);

        $clean = rtrim(self::prefix($locale).$clean, '/');

        return url($clean === '' ? '/' : $clean).$query;
    }
}
