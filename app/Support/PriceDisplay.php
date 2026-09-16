<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\Setting;

/**
 * Цена в валюте языка.
 *
 * Продавец назначает цену в своей валюте — в сумах, долларах, юанях.
 * Покупатель на китайской версии сайта хочет видеть юани, а не
 * пересчитывать сумы в уме. Валюта показа привязана к языку и задаётся
 * в настройках площадки («Валюты»): русская и узбекская версии —
 * сумы, английская — доллары, китайская — юани, турецкая — лиры.
 *
 * Пересчёт — приблизительный, по курсу ЦБ, и витрина показывает его
 * со знаком «≈», а рядом — цену продавца как назначена: договор
 * заключают по ней, а не по курсу дня. Когда валюта продавца
 * совпадает с валютой языка или курса нет, пересчёта не бывает.
 */
final class PriceDisplay
{
    /** Ключ настройки: display_currency_en, display_currency_zh… */
    public const KEY_PREFIX = 'display_currency_';

    /**
     * Валюта языка, пока администратор не задал свою.
     *
     * @var array<string, string>
     */
    public const DEFAULTS = [
        'ru' => 'UZS',
        'uz' => 'UZS',
        'en' => 'USD',
        'zh' => 'CNY',
        'tr' => 'TRY',
    ];

    /**
     * Валюта языка на время запроса: настройка читается из кэша,
     * а карточек на странице десятки — по обращению на каждую
     * это десятки походов в Redis ради одного и того же значения.
     *
     * @var array<string, string>
     */
    private array $currencies = [];

    public function __construct(private readonly CurrencyRate $rate) {}

    public static function key(string $locale): string
    {
        return self::KEY_PREFIX.$locale;
    }

    public static function isKey(?string $key): bool
    {
        return $key !== null
            && str_starts_with($key, self::KEY_PREFIX)
            && Locales::supports(substr($key, strlen(self::KEY_PREFIX)));
    }

    /**
     * Валюта показа для языка.
     *
     * Значение из настройки проверяется по списку валют: код, которого
     * витрина не знает, дал бы «≈ 97 XXX» на каждой карточке.
     */
    public static function currency(?string $locale = null): string
    {
        $locale ??= app()->getLocale();
        $default = self::DEFAULTS[$locale] ?? self::DEFAULTS[Locales::DEFAULT];

        $chosen = Setting::get(self::key($locale));
        $chosen = is_string($chosen) ? strtoupper(trim($chosen)) : null;

        return Currencies::supports($chosen) ? $chosen : $default;
    }

    /**
     * Пересчёт цены продавца в валюту языка.
     *
     * null — показывать нечего: цены нет, валюта та же или курса нет.
     *
     * @return array{price: float, currency: string}|null
     */
    public function convert(float|int|string|null $amount, ?string $from, ?string $locale = null): ?array
    {
        if ($amount === null || $from === null) {
            return null;
        }

        $locale ??= app()->getLocale();
        $to = $this->currencies[$locale] ??= self::currency($locale);

        if ($to === $from) {
            return null;
        }

        $converted = $this->rate->convert((float) $amount, $from, $to);

        if ($converted === null) {
            return null;
        }

        $rounded = self::round($converted);

        // Меньше копейки: «≈ $0» за пакет по 30 сум — не цена,
        // а насмешка. Покупатель видит цену продавца как есть
        if ($rounded <= 0.0) {
            return null;
        }

        return ['price' => $rounded, 'currency' => $to];
    }

    /**
     * Округление до трёх значащих цифр, но не мельче копеек.
     *
     * Пересчитанная цена приблизительна, и хвост вроде «1 250 048 сум»
     * обещает точность, которой нет: 1 250 000. Мелкие цены сохраняют
     * копейки: кирпич за $0,74 нельзя показать как $1.
     */
    public static function round(float $value): float
    {
        if ($value <= 0.0) {
            return 0.0;
        }

        // Отрицательная точность округляет до десятков, тысяч и т. д.
        $digits = 2 - (int) floor(log10($value));

        return round($value, min(2, $digits));
    }
}
