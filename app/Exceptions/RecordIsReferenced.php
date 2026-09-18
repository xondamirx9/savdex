<?php

declare(strict_types=1);

namespace App\Exceptions;

use RuntimeException;

/**
 * Запись нельзя удалить: на неё ссылаются живые данные.
 *
 * Возникает на справочниках географии. Внешние ключи там устроены так,
 * что база не сопротивляется: города уходят каскадом, а у компаний,
 * объявлений и тендеров адрес молча обнуляется. То есть промах в
 * админке стоил бы сотен записей без единого сообщения об ошибке
 * и без возможности откатить.
 */
class RecordIsReferenced extends RuntimeException
{
    /** @param  array<string, int>  $references  что ссылается => сколько */
    public function __construct(public readonly array $references)
    {
        parent::__construct('На запись ссылаются: '.self::describe($references));
    }

    /** @param  array<string, int>  $references */
    public static function describe(array $references): string
    {
        $parts = [];

        foreach ($references as $what => $count) {
            $parts[] = "{$what} — {$count}";
        }

        return implode(', ', $parts);
    }
}
