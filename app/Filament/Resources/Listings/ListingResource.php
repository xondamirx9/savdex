<?php

namespace App\Filament\Resources\Listings;

use App\Filament\Resources\Listings\Pages\EditListing;
use App\Filament\Resources\Listings\Pages\ListListings;
use App\Filament\Resources\Listings\Schemas\ListingForm;
use App\Filament\Resources\Listings\Tables\ListingsTable;
use App\Models\Listing;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Schemas\Schema;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Model;
use Illuminate\Database\Eloquent\SoftDeletingScope;
use Illuminate\Support\Facades\Auth;

class ListingResource extends Resource
{
    protected static ?string $model = Listing::class;

    protected static ?string $navigationLabel = 'Объявления';

    protected static ?string $modelLabel = 'объявление';

    protected static ?string $pluralModelLabel = 'объявления';

    protected static string|\UnitEnum|null $navigationGroup = 'Данные';

    protected static ?int $navigationSort = 2;

    /** Счётчик очереди модерации: сюда заходят именно за ней. */
    public static function getNavigationBadge(): ?string
    {
        $count = Listing::where('status', Listing::STATUS_MODERATION)->count();

        return $count > 0 ? (string) $count : null;
    }

    public static function getNavigationBadgeColor(): ?string
    {
        return 'warning';
    }

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedRectangleStack;

    /**
     * Инструмент модератора — «Отклонить», а не «Удалить».
     *
     * Отказ снимает объявление с витрины и объясняет владельцу причину;
     * удаление просто убирает его без следа, и человек видит пустоту
     * вместо ответа. Для запрещённого товара отказа достаточно: из
     * выдачи объявление исчезает сразу. Удаление, тем более массовое
     * и безвозвратное, оставлено суперадмину.
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
        return ListingForm::configure($schema);
    }

    public static function table(Table $table): Table
    {
        return ListingsTable::configure($table);
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
            'index' => ListListings::route('/'),
            'edit' => EditListing::route('/{record}/edit'),
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
