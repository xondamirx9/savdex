<?php

declare(strict_types=1);

namespace App\Support;

use OpenSpout\Common\Entity\Row;
use OpenSpout\Writer\XLSX\Writer;

/**
 * Образец книги для загрузки товаров.
 *
 * Заказчик собирает каталог руками, и проще дать готовый файл, чем
 * описывать словами, как назвать столбцы и листы. Книга — пять
 * листов, по одному на язык сайта: русский главный, с ценами
 * и фотографиями, остальные — только тексты, строка к строке.
 *
 * Загрузка узнаёт столбцы и на других языках (ImportLanguage), так
 * что переименовывать «Название» в «Product» не запрещено, — образец
 * просто избавляет от догадок.
 */
final class ListingWorkbookTemplate
{
    /** @var list<string> */
    public const HEADERS = [
        'Номер', 'Название', 'Компания', 'Категория', 'Тип', 'Цена', 'Валюта',
        'Единица', 'Минимальный заказ', 'Город', 'Описание',
        'Условия поставки', 'Условия оплаты', 'Фото',
    ];

    /** @var list<string> */
    private const EXAMPLE = [
        '', 'Кирпич керамический М150', 'ООО «Стройбаза»', 'Стройматериалы → Кирпич и блоки',
        'Предложение', '1200', 'UZS', 'шт', '5000', 'Ташкент',
        'Полнотелый, марка М150, отгрузка с завода.',
        'Самовывоз со склада, доставка по Ташкентской области.',
        'Предоплата 50 %, остаток по факту отгрузки.', '',
    ];

    /**
     * Языковые листы: имя вкладки, столбцы и пример — на своём языке.
     *
     * Имена вкладок — те же, что в переключателе языка на сайте:
     * человек, который заполняет книгу, видит их каждый день.
     *
     * @var array<string, array{headers: list<string>, example: list<string>}>
     */
    private const TRANSLATIONS = [
        'en' => [
            'headers' => ['Title', 'Description', 'Delivery terms', 'Payment terms'],
            'example' => [
                'Ceramic brick M150', 'Solid, grade M150, shipped from the plant.',
                'Pick-up from the warehouse, delivery across the Tashkent region.',
                '50 % prepayment, the rest on shipment.',
            ],
        ],
        'uz' => [
            'headers' => ['Nomi', 'Tavsif', 'Yetkazib berish shartlari', "To'lov shartlari"],
            'example' => [
                'Keramik g‘isht M150', 'To‘liq, M150 markasi, zavoddan jo‘natish.',
                'Ombordan o‘zi olib ketish, Toshkent viloyati bo‘ylab yetkazish.',
                '50 % oldindan to‘lov, qolgani jo‘natish bo‘yicha.',
            ],
        ],
        'zh' => [
            'headers' => ['名称', '描述', '交货条件', '付款条件'],
            'example' => [
                'M150 陶瓷砖', '实心砖，M150 标号，工厂直发。',
                '仓库自提，塔什干州范围内配送。',
                '预付 50 %，余款发货后结清。',
            ],
        ],
        'tr' => [
            'headers' => ['Başlık', 'Açıklama', 'Teslimat koşulları', 'Ödeme koşulları'],
            'example' => [
                'Seramik tuğla M150', 'Dolu, M150 sınıfı, fabrikadan sevkiyat.',
                'Depodan teslim, Taşkent bölgesine dağıtım.',
                '%50 peşin, kalanı sevkiyatta.',
            ],
        ],
    ];

    public static function write(string $path): void
    {
        $writer = new Writer;
        $writer->openToFile($path);

        try {
            $writer->getCurrentSheet()->setName(self::sheetName('ru'));
            $writer->addRow(Row::fromValues(self::HEADERS));
            $writer->addRow(Row::fromValues(self::EXAMPLE));

            foreach (self::TRANSLATIONS as $locale => $sheet) {
                $writer->addNewSheetAndMakeItCurrent()->setName(self::sheetName($locale));
                $writer->addRow(Row::fromValues($sheet['headers']));
                $writer->addRow(Row::fromValues($sheet['example']));
            }
        } finally {
            $writer->close();
        }
    }

    /** Имя вкладки языка — как в переключателе на сайте. */
    public static function sheetName(string $locale): string
    {
        return Locales::ALL[$locale]['label'];
    }
}
