<?php

declare(strict_types=1);

namespace App\Support;

use App\Models\User;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Support\Facades\Auth;

/**
 * Сужение списка до «своих записей».
 *
 * Право открывает раздел, область видимости решает, сколько в нём видно.
 * Продавец видит своих лидов, руководитель — всех, и это одна и та же
 * страница с одним и тем же правом.
 *
 * Сужение делается запросом, а не скрытием строк после выборки: чужая
 * запись не должна попасть ни в список, ни в счётчик, ни в выгрузку.
 */
final class AdminScope
{
    /**
     * @param  string  $section  раздел прав, у которого спрашивается область
     * @param  string  $column  колонка с ответственным
     * @param  bool  $orphansVisible  видна ли запись без ответственного
     */
    public static function apply(
        Builder $query,
        string $section,
        string $column,
        bool $orphansVisible = false,
    ): Builder {
        $user = Auth::user();

        if (! $user instanceof User || ! $user->adminScopeIsOwn($section)) {
            return $query;
        }

        return $query->where(function (Builder $q) use ($column, $user, $orphansVisible): void {
            $q->where($column, $user->getKey());

            /*
             * Нераспределённая заявка видна всем.
             *
             * Иначе новый лид пролежит до первого распределения, а
             * звонить по нему надо сегодня. Как только продавец берёт
             * лид себе, тот пропадает из общего списка.
             */
            if ($orphansVisible) {
                $q->orWhereNull($column);
            }
        });
    }

    /**
     * Может ли текущий сотрудник трогать эту запись.
     *
     * Проверка на уровне записи, а не списка: скрытая строка защищает
     * от случайности, а прямая ссылка на чужую карточку — нет.
     */
    public static function owns(string $section, ?int $ownerId): bool
    {
        $user = Auth::user();

        if (! $user instanceof User) {
            return false;
        }

        if (! $user->adminScopeIsOwn($section)) {
            return true;
        }

        return $ownerId === null || $ownerId === $user->getKey();
    }
}
