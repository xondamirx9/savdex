<?php

namespace App\Filament\Resources\Broadcasts;

use App\Filament\Resources\Broadcasts\Pages\CreateBroadcast;
use App\Filament\Resources\Broadcasts\Pages\EditBroadcast;
use App\Filament\Resources\Broadcasts\Pages\ListBroadcasts;
use App\Filament\Resources\Broadcasts\Schemas\BroadcastForm;
use App\Filament\Resources\Broadcasts\Tables\BroadcastsTable;
use App\Models\Broadcast;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Schemas\Schema;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;
use Illuminate\Support\Facades\Auth;

class BroadcastResource extends Resource
{
    protected static ?string $model = Broadcast::class;

    protected static ?string $navigationLabel = 'Рассылки';

    protected static ?string $modelLabel = 'рассылка';

    protected static ?string $pluralModelLabel = 'рассылки';

    protected static string|\UnitEnum|null $navigationGroup = 'Система';

    protected static ?int $navigationSort = 2;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedRectangleStack;

    /**
     * Рассылка уходит тысячам людей и не отзывается.
     */
    public static function canViewAny(): bool
    {
        return Auth::user()?->isSuperadmin() ?? false;
    }

    public static function form(Schema $schema): Schema
    {
        return BroadcastForm::configure($schema);
    }

    public static function table(Table $table): Table
    {
        return BroadcastsTable::configure($table);
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
            'index' => ListBroadcasts::route('/'),
            'create' => CreateBroadcast::route('/create'),
            'edit' => EditBroadcast::route('/{record}/edit'),
        ];
    }
}
