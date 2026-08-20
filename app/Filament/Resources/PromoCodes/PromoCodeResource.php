<?php

declare(strict_types=1);

namespace App\Filament\Resources\PromoCodes;

use App\Filament\Resources\PromoCodes\Pages\ListPromoCodes;
use App\Filament\Resources\PromoCodes\Tables\PromoCodesTable;
use App\Models\PromoCode;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;
use Illuminate\Support\Facades\Auth;
use UnitEnum;

/**
 * Промокоды на бесплатный период тарифа.
 *
 * Формы создания нет намеренно: коды не придумывают руками, а выпускают
 * пачкой — действием «Выпустить коды» в шапке списка. Код, набранный
 * человеком, предсказуем, а угаданный промокод — это выданный бесплатно
 * месяц тарифа.
 *
 * Правится в списке только выключатель: срок и тариф выпущенного кода
 * менять нельзя — он уже роздан на руки под конкретную акцию.
 */
class PromoCodeResource extends Resource
{
    protected static ?string $model = PromoCode::class;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedGift;

    protected static ?string $navigationLabel = 'Промокоды';

    protected static ?string $modelLabel = 'промокод';

    protected static ?string $pluralModelLabel = 'промокоды';

    protected static string|UnitEnum|null $navigationGroup = 'Монетизация';

    protected static ?int $navigationSort = 5;

    public static function canViewAny(): bool
    {
        return Auth::user()?->isSuperadmin() ?? false;
    }

    public static function table(Table $table): Table
    {
        return PromoCodesTable::configure($table);
    }

    public static function getPages(): array
    {
        return [
            'index' => ListPromoCodes::route('/'),
        ];
    }
}
