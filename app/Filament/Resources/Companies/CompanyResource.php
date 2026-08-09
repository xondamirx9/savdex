<?php

namespace App\Filament\Resources\Companies;

use App\Filament\Resources\Companies\Pages\CreateCompany;
use App\Filament\Resources\Companies\Pages\EditCompany;
use App\Filament\Resources\Companies\Pages\ListCompanies;
use App\Filament\Resources\Companies\Schemas\CompanyForm;
use App\Filament\Resources\Companies\Tables\CompaniesTable;
use App\Models\Company;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Schemas\Schema;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\SoftDeletingScope;
use Illuminate\Support\Facades\Auth;

class CompanyResource extends Resource
{
    protected static ?string $model = Company::class;

    protected static ?string $navigationLabel = 'Компании';

    protected static ?string $modelLabel = 'компания';

    protected static ?string $pluralModelLabel = 'компании';

    protected static string|\UnitEnum|null $navigationGroup = 'Данные';

    protected static ?int $navigationSort = 1;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedRectangleStack;

    /**
     * Удаление компании — не модерация.
     *
     * Модератор смотрит содержание: карточку правит, нарушителя
     * блокирует. Удаление уносит вместе с компанией кошелёк, подписку
     * и раскрытые контакты, за которые заплачено, а массовое действие
     * делает это по галочкам сразу с полусотней. Право оставлено
     * суперадмину; модератору для его задач хватает блокировки.
     */
    public static function canDelete(Model $record): bool
    {
        return Auth::user()?->isSuperadmin() ?? false;
    }

    public static function canDeleteAny(): bool
    {
        return Auth::user()?->isSuperadmin() ?? false;
    }

    public static function canForceDelete(Model $record): bool
    {
        return Auth::user()?->isSuperadmin() ?? false;
    }

    public static function canRestore(Model $record): bool
    {
        return Auth::user()?->isSuperadmin() ?? false;
    }

    public static function form(Schema $schema): Schema
    {
        return CompanyForm::configure($schema);
    }

    public static function table(Table $table): Table
    {
        return CompaniesTable::configure($table);
    }

    public static function getRelations(): array
    {
        return [
            //
        ];
    }

    public static function getPages(): array
    {
        return [
            'index' => ListCompanies::route('/'),
            'create' => CreateCompany::route('/create'),
            'edit' => EditCompany::route('/{record}/edit'),
        ];
    }

    public static function getRecordRouteBindingEloquentQuery(): Builder
    {
        return parent::getRecordRouteBindingEloquentQuery()
            ->withoutGlobalScopes([
                SoftDeletingScope::class,
            ]);
    }
}
