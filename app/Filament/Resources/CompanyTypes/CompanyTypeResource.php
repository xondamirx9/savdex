<?php

declare(strict_types=1);

namespace App\Filament\Resources\CompanyTypes;

use App\Filament\Resources\CompanyTypes\Pages\CreateCompanyType;
use App\Filament\Resources\CompanyTypes\Pages\EditCompanyType;
use App\Filament\Resources\CompanyTypes\Pages\ListCompanyTypes;
use App\Filament\Resources\CompanyTypes\Schemas\CompanyTypeForm;
use App\Filament\Resources\CompanyTypes\Tables\CompanyTypesTable;
use App\Models\CompanyType;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Schemas\Schema;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;
use Illuminate\Support\Facades\Auth;
use UnitEnum;

class CompanyTypeResource extends Resource
{
    protected static ?string $model = CompanyType::class;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedBuildingOffice2;

    protected static ?string $navigationLabel = 'Типы компаний';

    protected static ?string $modelLabel = 'тип компании';

    protected static ?string $pluralModelLabel = 'типы компаний';

    protected static string|UnitEnum|null $navigationGroup = 'Справочники';

    protected static ?int $navigationSort = 2;

    public static function getNavigationBadge(): ?string
    {
        return (string) CompanyType::count();
    }

    /**
     * Тип компании — поле формы регистрации, а не объект модерации:
     * правит его тот, кто отвечает за устройство площадки.
     */
    public static function canViewAny(): bool
    {
        return Auth::user()?->isSuperadmin() ?? false;
    }

    public static function form(Schema $schema): Schema
    {
        return CompanyTypeForm::configure($schema);
    }

    public static function table(Table $table): Table
    {
        return CompanyTypesTable::configure($table);
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
            'index' => ListCompanyTypes::route('/'),
            'create' => CreateCompanyType::route('/create'),
            'edit' => EditCompanyType::route('/{record}/edit'),
        ];
    }
}
