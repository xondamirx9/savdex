<?php

declare(strict_types=1);

namespace App\Filament\Resources\AdminActions;

use App\Filament\Concerns\AuthorizesBySection;
use App\Filament\Resources\AdminActions\Pages\ListAdminActions;
use App\Filament\Resources\AdminActions\Tables\AdminActionsTable;
use App\Models\AdminAction;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Model;
use UnitEnum;

/**
 * Журнал действий администраторов — только чтение.
 *
 * Ни создать, ни изменить, ни удалить: журнал, который можно подчистить,
 * защищает ровно до того момента, когда он понадобится. Запрет продублирован
 * в самой модели, потому что права закрывают панель, а модель — ещё и
 * команду в консоли.
 */
class AdminActionResource extends Resource
{
    use AuthorizesBySection;

    protected static string $accessSection = 'audit';

    protected static ?string $model = AdminAction::class;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedClipboardDocumentList;

    protected static ?string $navigationLabel = 'Журнал действий';

    protected static ?string $modelLabel = 'запись журнала';

    protected static ?string $pluralModelLabel = 'записи журнала';

    protected static string|UnitEnum|null $navigationGroup = 'Система';

    protected static ?int $navigationSort = 4;

    public static function canCreate(): bool
    {
        return false;
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

    public static function canRestore(Model $record): bool
    {
        return false;
    }

    public static function canRestoreAny(): bool
    {
        return false;
    }

    public static function table(Table $table): Table
    {
        return AdminActionsTable::configure($table);
    }

    public static function getPages(): array
    {
        return [
            'index' => ListAdminActions::route('/'),
        ];
    }
}
