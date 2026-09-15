<?php

declare(strict_types=1);

namespace App\Support;

use SimpleXMLElement;
use ZipArchive;

/**
 * Фотографии, вставленные в лист Excel, разложенные по строкам.
 *
 * Готовых библиотек для этого в проекте нет: openspout читает значения
 * ячеек и ничего не знает о картинках, а тянуть PhpSpreadsheet целиком
 * ради одной операции — полсотни мегабайт зависимостей.
 *
 * Разбор несложный, потому что xlsx — обычный zip с XML внутри:
 *
 *   xl/workbook.xml            — список листов;
 *   xl/worksheets/sheetN.xml   — ячейки, там же ссылка на рисунки;
 *   xl/drawings/drawingN.xml   — где какая картинка стоит (строка и колонка);
 *   xl/media/imageN.png        — сами файлы.
 *
 * Связи между частями лежат отдельно, в файлах _rels: в XML стоит
 * идентификатор вида «rId3», а какой файл за ним — написано там.
 *
 * Картинка привязана к ячейке верхним левым углом: фотография может
 * налезать на соседние строки, но принадлежит той, где её угол.
 */
final class WorkbookImages
{
    private const RELS = 'http://schemas.openxmlformats.org/package/2006/relationships';

    private const DOC_RELS = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships';

    private const DRAWING = 'http://schemas.openxmlformats.org/drawingml/2006/spreadsheetDrawing';

    private const MAIN = 'http://schemas.openxmlformats.org/drawingml/2006/main';

    private const SHEET = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main';

    /**
     * Разобрать книгу и сложить картинки первого листа в каталог.
     *
     * Файлы кладутся на диск, а не держатся в памяти: сотня фотографий
     * по три мегабайта — это триста мегабайт, и процесс падает на
     * половине книги.
     *
     * @return array<int, list<string>> номер строки (с единицы) → пути к файлам
     */
    public static function extract(string $workbook, string $into): array
    {
        $zip = new ZipArchive;

        if ($zip->open($workbook) !== true) {
            return [];
        }

        try {
            $sheet = self::firstSheetPath($zip);

            if ($sheet === null) {
                return [];
            }

            $drawing = self::relatedPart($zip, $sheet, 'drawing');

            if ($drawing === null) {
                return [];
            }

            $xml = self::xml($zip, $drawing);

            if ($xml === null) {
                return [];
            }

            $media = self::relationTargets($zip, $drawing);
            $rows = [];

            foreach ($xml->children(self::DRAWING) as $anchor) {
                $placed = self::anchored($anchor, $media);

                if ($placed === null) {
                    continue;
                }

                [$row, $column, $part] = $placed;
                $rows[$row][] = ['column' => $column, 'part' => $part];
            }

            return self::save($zip, $rows, $into);
        } finally {
            $zip->close();
        }
    }

    /**
     * Строка, колонка и файл картинки одного якоря.
     *
     * @param  array<string, string>  $media
     * @return array{0: int, 1: int, 2: string}|null
     */
    private static function anchored(SimpleXMLElement $anchor, array $media): ?array
    {
        $from = $anchor->children(self::DRAWING)->from;

        // absoluteAnchor привязан к листу, а не к ячейке: к какой строке
        // относится такая картинка, неизвестно даже на глаз
        if ($from->count() === 0) {
            return null;
        }

        $picture = $anchor->children(self::DRAWING)->pic;

        if ($picture->count() === 0) {
            return null;
        }

        $blip = $picture->children(self::DRAWING)->blipFill->children(self::MAIN)->blip;

        if ($blip->count() === 0) {
            return null;
        }

        $id = (string) $blip->attributes(self::DOC_RELS)->embed;
        $part = $media[$id] ?? null;

        if ($part === null) {
            return null;
        }

        $corner = $from->children(self::DRAWING);

        // В файле строки и колонки считаются от нуля, а человек говорит
        // «вторая строка» про ту, что в Excel помечена двойкой
        return [((int) $corner->row) + 1, (int) $corner->col, $part];
    }

    /**
     * Достать файлы из книги и разложить по строкам.
     *
     * @param  array<int, list<array{column: int, part: string}>>  $rows
     * @return array<int, list<string>>
     */
    private static function save(ZipArchive $zip, array $rows, string $into): array
    {
        if (! is_dir($into) && ! mkdir($into, 0755, true) && ! is_dir($into)) {
            return [];
        }

        $saved = [];
        $number = 0;

        ksort($rows);

        foreach ($rows as $row => $pictures) {
            // Фотографии одной строки идут в том порядке, в каком стоят
            // в таблице: первая становится обложкой объявления
            usort($pictures, fn (array $a, array $b): int => $a['column'] <=> $b['column']);

            foreach ($pictures as $picture) {
                $binary = $zip->getFromName($picture['part']);

                if ($binary === false || $binary === '') {
                    continue;
                }

                $path = rtrim($into, '/').'/'.(++$number).'-'.basename($picture['part']);

                if (file_put_contents($path, $binary) !== false) {
                    $saved[$row][] = $path;
                }
            }
        }

        return $saved;
    }

    /** Путь к XML первого листа книги. */
    private static function firstSheetPath(ZipArchive $zip): ?string
    {
        $workbook = self::xml($zip, 'xl/workbook.xml');

        if ($workbook === null) {
            return null;
        }

        /*
         * Пространство имён указывается на каждом шаге.
         *
         * SimpleXML помнит его ровно один уровень: children() отдаёт
         * <sheets>, но у полученного узла обращение ->sheet ищет уже
         * в пустом пространстве и возвращает ничего.
         */
        $sheets = $workbook->children(self::SHEET)->sheets;
        $sheet = $sheets->children(self::SHEET)->sheet[0] ?? null;

        if ($sheet === null) {
            return null;
        }

        $id = (string) $sheet->attributes(self::DOC_RELS)->id;

        return self::relationTargets($zip, 'xl/workbook.xml')[$id] ?? null;
    }

    /** Часть книги, на которую ссылается другая часть: рисунки листа. */
    private static function relatedPart(ZipArchive $zip, string $part, string $type): ?string
    {
        $rels = self::xml($zip, self::relsPath($part));

        if ($rels === null) {
            return null;
        }

        foreach ($rels->children(self::RELS) as $relation) {
            if (str_ends_with(self::attribute($relation, 'Type'), '/'.$type)) {
                return self::resolve($part, self::attribute($relation, 'Target'));
            }
        }

        return null;
    }

    /**
     * Идентификатор связи → путь к файлу внутри книги.
     *
     * @return array<string, string>
     */
    private static function relationTargets(ZipArchive $zip, string $part): array
    {
        $rels = self::xml($zip, self::relsPath($part));

        if ($rels === null) {
            return [];
        }

        $targets = [];

        foreach ($rels->children(self::RELS) as $relation) {
            // Внешние картинки по ссылке пропускаем: в книге их нет,
            // а ходить за ними в интернет загрузка не должна
            if (self::attribute($relation, 'TargetMode') === 'External') {
                continue;
            }

            $targets[self::attribute($relation, 'Id')] = self::resolve($part, self::attribute($relation, 'Target'));
        }

        return $targets;
    }

    /**
     * Атрибут без префикса.
     *
     * Через $node['Id'] его не достать: узел получен из children()
     * с пространством имён, и SimpleXML ищет атрибут там же, а Id
     * и Target объявлены без пространства — и возвращается пустота.
     */
    private static function attribute(SimpleXMLElement $node, string $name): string
    {
        return (string) ($node->attributes()[$name] ?? '');
    }

    private static function relsPath(string $part): string
    {
        $directory = dirname($part);
        $directory = $directory === '.' ? '' : $directory.'/';

        return $directory.'_rels/'.basename($part).'.rels';
    }

    /** Ссылка внутри книги задаётся относительно той части, где написана. */
    private static function resolve(string $part, string $target): string
    {
        if (str_starts_with($target, '/')) {
            return ltrim($target, '/');
        }

        $segments = [];

        foreach (explode('/', dirname($part).'/'.$target) as $segment) {
            if ($segment === '' || $segment === '.') {
                continue;
            }

            if ($segment === '..') {
                array_pop($segments);

                continue;
            }

            $segments[] = $segment;
        }

        return implode('/', $segments);
    }

    private static function xml(ZipArchive $zip, string $part): ?SimpleXMLElement
    {
        if ($part === '') {
            return null;
        }

        $source = $zip->getFromName($part);

        if ($source === false || trim($source) === '') {
            return null;
        }

        // Чужой файл. LIBXML_NONET запрещает загрузку по сети, а
        // подстановка сущностей (LIBXML_NOENT) не включается: именно
        // она превращает книгу с «безобидным» XML в чтение файлов
        // сервера и в бомбу из вложенных сущностей
        $xml = @simplexml_load_string($source, SimpleXMLElement::class, LIBXML_NONET);

        return $xml === false ? null : $xml;
    }
}
