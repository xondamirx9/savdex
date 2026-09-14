<?php

declare(strict_types=1);

namespace App\Filament\Imports\Concerns;

use App\Support\ImportLanguage;

/**
 * Разбор заголовков файла на любом языке.
 *
 * Filament подставляет соответствие столбцов в окне импорта точным
 * сравнением с подсказками, поэтому «Kategoriya», «Company name» или
 * «Категория » с лишним пробелом остаются несопоставленными — а
 * несопоставленный столбец загружается молча и без ошибки.
 *
 * Здесь то, что осталось пустым, добирается по словарю синонимов:
 * окно импорта отвечает за предпросмотр, а этот разбор — за то, что
 * данные не потеряются, даже если менеджер ничего в окне не трогал.
 */
trait MapsHeadersInAnyLanguage
{
    /**
     * Синонимы заголовков: имя столбца → как его называют в таблицах.
     *
     * @return array<string, list<string>>
     */
    abstract protected static function headerAliases(): array;

    public function remapData(): void
    {
        $taken = array_values(array_filter($this->columnMap));

        foreach (static::headerAliases() as $column => $aliases) {
            if (filled($this->columnMap[$column] ?? null)) {
                continue;
            }

            foreach (array_keys($this->data) as $header) {
                $header = (string) $header;

                if (in_array($header, $taken, true) || ! ImportLanguage::matches($header, $aliases)) {
                    continue;
                }

                $this->columnMap[$column] = $header;
                $taken[] = $header;

                break;
            }
        }

        parent::remapData();
    }
}
