<?php

declare(strict_types=1);

namespace App\Filament\Widgets;

use App\Models\User;
use Filament\Widgets\Widget;
use Illuminate\Support\Facades\Auth;

/**
 * Объяснение тому, кому ещё не назначили роль.
 *
 * Между «человека завели в панель» и «человеку выдали роль» проходит
 * время, иногда дни. Разделы всё это время закрыты правильно — но
 * человек видел пустой экран без единого слова и решал, что панель
 * сломалась: писал в поддержку, заводил второй аккаунт, пробовал
 * другой браузер.
 *
 * Пустота без объяснения — это не защита, а недоделка рядом с ней.
 */
class AwaitingRole extends Widget
{
    protected string $view = 'filament.widgets.awaiting-role';

    protected int|string|array $columnSpan = 'full';

    /** Выше всех остальных: если он показан, других виджетов всё равно нет. */
    protected static ?int $sort = -100;

    /*
     * Без ленивой загрузки: Filament догружает виджеты отдельным
     * запросом к серверу, а здесь показывается неизменная надпись
     * без единого обращения к базе. Лишний поход туда и обратно —
     * это ещё несколько сотен миллисекунд перед объяснением того,
     * почему экран пуст.
     */
    protected static bool $isLazy = false;

    public static function canView(): bool
    {
        $user = Auth::user();

        if (! $user instanceof User || ! $user->is_admin || $user->status !== 'active') {
            return false;
        }

        /*
         * Проверяются права, а не пустая роль: роль может быть назначена,
         * но все её права сняты персональной настройкой — человек увидит
         * ту же пустоту и не должен остаться без объяснения.
         */
        return ! $user->isSuperadmin() && $user->adminAbilities() === [];
    }
}
