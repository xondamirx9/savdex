<?php

declare(strict_types=1);

namespace App\Filament\Resources\CreditPacks;

use App\Filament\Resources\CreditPacks\Pages\CreateCreditPack;
use App\Filament\Resources\CreditPacks\Pages\EditCreditPack;
use App\Filament\Resources\CreditPacks\Pages\ListCreditPacks;
use App\Filament\Resources\CreditPacks\Schemas\CreditPackForm;
use App\Filament\Resources\CreditPacks\Tables\CreditPacksTable;
use App\Models\CreditPack;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Schemas\Schema;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;
use Illuminate\Support\Facades\Auth;
use UnitEnum;

/**
 * Пакеты кредитов — то же, что тарифы: цены площадки.
 * Правит их суперадмин, модератору здесь делать нечего.
 */
class CreditPackResource extends Resource
{
    protected static ?string $model = CreditPack::class;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedTicket;

    protected static ?string $navigationLabel = 'Пакеты контактов';

    protected static ?string $modelLabel = 'пакет';

    protected static ?string $pluralModelLabel = 'пакеты';

    protected static string|UnitEnum|null $navigationGroup = 'Монетизация';

    protected static ?int $navigationSort = 4;

    public static function canViewAny(): bool
    {
        return Auth::user()?->isSuperadmin() ?? false;
    }

    public static function form(Schema $schema): Schema
    {
        return CreditPackForm::configure($schema);
    }

    public static function table(Table $table): Table
    {
        return CreditPacksTable::configure($table);
    }

    public static function getPages(): array
    {
        return [
            'index' => ListCreditPacks::route('/'),
            'create' => CreateCreditPack::route('/create'),
            'edit' => EditCreditPack::route('/{record}/edit'),
        ];
    }
}
