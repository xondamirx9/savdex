<?php

declare(strict_types=1);

namespace App\Filament\Resources\Countries;

use App\Filament\Concerns\AuthorizesBySection;
use App\Filament\Resources\Countries\Pages\CreateCountry;
use App\Filament\Resources\Countries\Pages\EditCountry;
use App\Filament\Resources\Countries\Pages\ListCountries;
use App\Filament\Resources\Countries\Schemas\CountryForm;
use App\Filament\Resources\Countries\Tables\CountriesTable;
use App\Models\Country;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Schemas\Schema;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;
use UnitEnum;

/**
 * Страны площадки.
 *
 * Список, из которого компания выбирает страну при регистрации. До
 * этого экрана он правился только сидером — то есть деплоем, а значит
 * новое направление ждало разработчика.
 */
class CountryResource extends Resource
{
    use AuthorizesBySection;

    protected static string $accessSection = 'catalogs';

    protected static ?string $model = Country::class;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedGlobeAlt;

    protected static ?string $navigationLabel = 'Страны';

    protected static ?string $modelLabel = 'страна';

    protected static ?string $pluralModelLabel = 'страны';

    protected static string|UnitEnum|null $navigationGroup = 'Справочники';

    protected static ?int $navigationSort = 3;

    /** Счётчик в меню показывает объём справочника без захода внутрь. */
    public static function getNavigationBadge(): ?string
    {
        return (string) Country::count();
    }

    public static function form(Schema $schema): Schema
    {
        return CountryForm::configure($schema);
    }

    public static function table(Table $table): Table
    {
        return CountriesTable::configure($table);
    }

    public static function getPages(): array
    {
        return [
            'index' => ListCountries::route('/'),
            'create' => CreateCountry::route('/create'),
            'edit' => EditCountry::route('/{record}/edit'),
        ];
    }
}
