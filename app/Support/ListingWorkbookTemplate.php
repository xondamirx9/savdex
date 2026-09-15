<?php

declare(strict_types=1);

namespace App\Support;

use OpenSpout\Common\Entity\Row;
use OpenSpout\Writer\XLSX\Writer;

/**
 * Образец книги для загрузки товаров.
 *
 * Заказчик собирает каталог руками, и проще дать готовый файл, чем
 * описывать словами, как назвать столбцы. Заголовки здесь те же, что
 * в выгрузке объявлений: выгрузил, дописал фотографии — загрузил.
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
        'Единица', 'Минимальный заказ', 'Город', 'Описание', 'Опубликовать', 'Фото',
    ];

    /** @var list<string> */
    private const EXAMPLE = [
        '', 'Кирпич керамический М150', 'ООО «Стройбаза»', 'Стройматериалы → Кирпич и блоки',
        'Предложение', '1200', 'UZS', 'шт', '5000', 'Ташкент',
        'Полнотелый, марка М150, отгрузка с завода.', 'да', '',
    ];

    public static function write(string $path): void
    {
        $writer = new Writer;
        $writer->openToFile($path);

        try {
            $writer->addRow(Row::fromValues(self::HEADERS));
            $writer->addRow(Row::fromValues(self::EXAMPLE));
        } finally {
            $writer->close();
        }
    }
}
