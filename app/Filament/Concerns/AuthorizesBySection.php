<?php

declare(strict_types=1);

namespace App\Filament\Concerns;

use App\Support\AdminAccess;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Support\Facades\Auth;

/**
 * Права ресурса берутся из матрицы, а не пишутся в самом ресурсе.
 *
 * Ресурс объявляет только, к какому разделу прав он относится:
 *
 *     protected static string $accessSection = 'companies';
 *
 * Всё остальное — кто может смотреть, создавать, править и удалять —
 * решает AdminAccess. Так не бывает ресурса, где право на создание
 * забыли объявить и оно досталось всем, кто вошёл в панель: именно
 * так и было у отзывов, тендеров, IT-задач и документов.
 *
 * Раздел объявлен свойством, а не методом, чтобы забытое объявление
 * ломалось сразу и заметно, а не выдавало доступ по умолчанию.
 */
trait AuthorizesBySection
{
    public static function canViewAny(): bool
    {
        return AdminAccess::allows(static::$accessSection.'.'.AdminAccess::VIEW);
    }

    public static function canView(Model $record): bool
    {
        return static::canViewAny();
    }

    /** Раздел в меню и в глобальном поиске. */
    public static function canAccess(): bool
    {
        return static::canViewAny();
    }

    public static function canCreate(): bool
    {
        return AdminAccess::allows(static::$accessSection.'.'.AdminAccess::CREATE);
    }

    public static function canEdit(Model $record): bool
    {
        return AdminAccess::allows(static::$accessSection.'.'.AdminAccess::EDIT);
    }

    /** Перетаскивание строк меняет порядок — это правка. */
    public static function canReorder(): bool
    {
        return AdminAccess::allows(static::$accessSection.'.'.AdminAccess::EDIT);
    }

    public static function canDelete(Model $record): bool
    {
        return AdminAccess::allows(static::$accessSection.'.'.AdminAccess::DELETE);
    }

    public static function canDeleteAny(): bool
    {
        return AdminAccess::allows(static::$accessSection.'.'.AdminAccess::DELETE);
    }

    /** Вернуть удалённое — та же власть, что и удалить. */
    public static function canRestore(Model $record): bool
    {
        return AdminAccess::allows(static::$accessSection.'.'.AdminAccess::DELETE);
    }

    public static function canRestoreAny(): bool
    {
        return AdminAccess::allows(static::$accessSection.'.'.AdminAccess::DELETE);
    }

    /**
     * Окончательное удаление — только суперадмину.
     *
     * Мягкое удаление обратимо, и потому это рабочее действие. Здесь же
     * запись уходит вместе со всем, что на неё ссылалось, и вернуть её
     * можно только из бэкапа — то есть не сегодня.
     */
    public static function canForceDelete(Model $record): bool
    {
        return Auth::user()?->isSuperadmin() ?? false;
    }

    public static function canForceDeleteAny(): bool
    {
        return Auth::user()?->isSuperadmin() ?? false;
    }
}
