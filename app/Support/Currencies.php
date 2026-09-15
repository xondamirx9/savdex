<?php

declare(strict_types=1);

namespace App\Support;

/**
 * Валюты, в которых продавец назначает цену.
 *
 * Список один на админку, кабинет и загрузку из книги: три места
 * с тремя разными наборами уже дали объявление в юанях, которое
 * форма админки не давала сохранить — юаня в её списке не было.
 */
final class Currencies
{
    /**
     * Код → как называется по-русски (админка — русская).
     *
     * @var array<string, string>
     */
    public const ALL = [
        'UZS' => 'сум',
        'USD' => 'доллар США',
        'EUR' => 'евро',
        'CNY' => 'юань',
        'TRY' => 'турецкая лира',
        'RUB' => 'рубль',
        'KZT' => 'тенге',
    ];

    /** @return list<string> */
    public static function codes(): array
    {
        return array_keys(self::ALL);
    }

    /** @return array<string, string> */
    public static function labels(): array
    {
        return self::ALL;
    }

    public static function supports(?string $code): bool
    {
        return $code !== null && array_key_exists($code, self::ALL);
    }
}
