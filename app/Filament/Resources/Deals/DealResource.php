<?php

declare(strict_types=1);

namespace App\Filament\Resources\Deals;

use App\Filament\Concerns\AuthorizesBySection;
use App\Filament\Resources\Deals\Pages\CreateDeal;
use App\Filament\Resources\Deals\Pages\EditDeal;
use App\Filament\Resources\Deals\Pages\ListDeals;
use App\Filament\Resources\Deals\Schemas\DealForm;
use App\Filament\Resources\Deals\Tables\DealsTable;
use App\Models\Crm\Deal;
use App\Support\AdminScope;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Schemas\Schema;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Model;
use UnitEnum;

/**
 * Сделки — работа с клиентом по конкретной сумме.
 *
 * Сделка без ответственного не бывает: она выросла из чьей-то работы.
 * Поэтому, в отличие от лидов, «ничьих» сделок в списке нет.
 */
class DealResource extends Resource
{
    use AuthorizesBySection;

    protected static string $accessSection = 'deals';

    protected static ?string $model = Deal::class;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedBriefcase;

    protected static ?string $navigationLabel = 'Сделки';

    protected static ?string $modelLabel = 'сделка';

    protected static ?string $pluralModelLabel = 'сделки';

    protected static string|UnitEnum|null $navigationGroup = 'CRM';

    protected static ?int $navigationSort = 2;

    public static function getEloquentQuery(): Builder
    {
        return AdminScope::apply(parent::getEloquentQuery(), 'deals', 'owner_id');
    }

    public static function canView(Model $record): bool
    {
        return parent::canView($record) && AdminScope::owns('deals', $record->owner_id);
    }

    public static function canEdit(Model $record): bool
    {
        return parent::canEdit($record) && AdminScope::owns('deals', $record->owner_id);
    }

    public static function canDelete(Model $record): bool
    {
        return parent::canDelete($record) && AdminScope::owns('deals', $record->owner_id);
    }

    public static function form(Schema $schema): Schema
    {
        return DealForm::configure($schema);
    }

    public static function table(Table $table): Table
    {
        return DealsTable::configure($table);
    }

    public static function getPages(): array
    {
        return [
            'index' => ListDeals::route('/'),
            'create' => CreateDeal::route('/create'),
            'edit' => EditDeal::route('/{record}/edit'),
        ];
    }
}
