<?php

declare(strict_types=1);

namespace App\Models\Concerns;

use App\Exceptions\RecordIsReferenced;

/**
 * Запись справочника не удаляется, пока на неё кто-то ссылается.
 *
 * Внешние ключи географии устроены так, что база удалению не мешает:
 * города уходят каскадом за страной, а у компаний, объявлений и
 * тендеров адрес обнуляется (nullOnDelete). То есть одно нажатие в
 * админке стоило бы сотен записей — молча, без ошибки и без отката.
 *
 * Проверка живёт в модели, а не в кнопке: кнопку обходят импорт,
 * консоль и любой будущий код, а событие deleting — нет.
 */
trait RefusesDeletionWhenReferenced
{
    /**
     * Что помешает удалению: «на что ссылается» => сколько штук.
     * Пустой массив — удалять можно.
     *
     * @return array<string, int>
     */
    abstract public function references(): array;

    protected static function bootRefusesDeletionWhenReferenced(): void
    {
        static::deleting(function (self $record): void {
            $references = $record->references();

            if ($references !== []) {
                throw new RecordIsReferenced($references);
            }
        });
    }

    public function isReferenced(): bool
    {
        return $this->references() !== [];
    }

    /** Человеческое перечисление для подсказки в админке. */
    public function referencesSummary(): string
    {
        return RecordIsReferenced::describe($this->references());
    }
}
