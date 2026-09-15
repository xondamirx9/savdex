<?php

declare(strict_types=1);

namespace App\Filament\Resources\Refunds;

use App\Filament\Concerns\AuthorizesBySection;
use App\Filament\Resources\Refunds\Pages\ListRefunds;
use App\Filament\Resources\Refunds\Tables\RefundsTable;
use App\Models\Refund;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Model;
use UnitEnum;

/**
 * Возвраты по платежам.
 *
 * Формы правки нет: возврат не редактируют, по нему принимают решение —
 * провести или отклонить. Оба решения требуют формулировки и попадают
 * в журнал.
 *
 * Удаления нет тоже. Ошибочный возврат исправляется обратной операцией,
 * а не стиранием записи: удалённый возврат ничем не отличается от
 * возврата, которого не было.
 */
class RefundResource extends Resource
{
    use AuthorizesBySection;

    protected static string $accessSection = 'refunds';

    protected static ?string $model = Refund::class;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedArrowUturnLeft;

    protected static ?string $navigationLabel = 'Возвраты';

    protected static ?string $modelLabel = 'возврат';

    protected static ?string $pluralModelLabel = 'возвраты';

    protected static string|UnitEnum|null $navigationGroup = 'Монетизация';

    protected static ?int $navigationSort = 3;

    /** Счётчик — заявленные: деньги, по которым решение ещё не принято. */
    public static function getNavigationBadge(): ?string
    {
        $count = Refund::where('status', Refund::STATUS_REQUESTED)->count();

        return $count > 0 ? (string) $count : null;
    }

    public static function getNavigationBadgeColor(): ?string
    {
        return 'danger';
    }

    public static function canEdit(Model $record): bool
    {
        return false;
    }

    public static function canDelete(Model $record): bool
    {
        return false;
    }

    public static function canDeleteAny(): bool
    {
        return false;
    }

    public static function canForceDelete(Model $record): bool
    {
        return false;
    }

    public static function canForceDeleteAny(): bool
    {
        return false;
    }

    public static function table(Table $table): Table
    {
        return RefundsTable::configure($table);
    }

    public static function getPages(): array
    {
        return [
            'index' => ListRefunds::route('/'),
        ];
    }
}
