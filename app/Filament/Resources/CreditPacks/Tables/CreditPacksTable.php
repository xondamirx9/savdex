<?php

declare(strict_types=1);

namespace App\Filament\Resources\CreditPacks\Tables;

use App\Models\CreditPack;
use App\Models\Payment;
use App\Support\CurrencyRate;
use Filament\Actions\EditAction;
use Filament\Tables\Columns\IconColumn;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Table;

class CreditPacksTable
{
    public static function configure(Table $table): Table
    {
        $rate = app(CurrencyRate::class)->usd();

        return $table
            ->columns([
                TextColumn::make('name')
                    ->label('Пакет')
                    ->description(fn (CreditPack $p): string => $p->code),

                TextColumn::make('credits')->label('Кредитов'),

                TextColumn::make('price_usd')
                    ->label('Цена')
                    ->state(fn (CreditPack $p): string => number_format($p->priceUzs($rate), 0, ',', ' ').' сум')
                    // Цена за контакт — то, чем пакеты сравнивают между собой
                    ->description(fn (CreditPack $p): string => number_format($p->perCredit($rate), 0, ',', ' ').' за контакт'),

                TextColumn::make('sold')
                    ->label('Продано')
                    ->state(fn (CreditPack $p): int => Payment::query()
                        ->where('credit_pack_id', $p->id)
                        ->where('status', 'paid')
                        ->count()),

                IconColumn::make('is_active')->label('Продаётся')->boolean(),
            ])
            ->defaultSort('sort')
            ->reorderable('sort')
            ->paginated(false)
            ->recordActions([EditAction::make()]);
        /*
         * Удаления нет: на пакет ссылаются выставленные счета, и его
         * исчезновение оставило бы оплату без объяснения, за что платили.
         */
    }
}
