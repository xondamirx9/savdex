<?php

declare(strict_types=1);

namespace App\Filament\Resources\Plans\Tables;

use App\Models\Plan;
use Filament\Actions\EditAction;
use Filament\Tables\Columns\IconColumn;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Table;

class PlansTable
{
    public static function configure(Table $table): Table
    {
        return $table
            ->modifyQueryUsing(fn ($query) => $query->withCount([
                'subscriptions as active_count' => fn ($q) => $q->where('status', 'active'),
            ]))
            ->columns([
                TextColumn::make('name')
                    ->label('Тариф')
                    ->description(fn (Plan $record): string => $record->code)
                    ->sortable(),

                TextColumn::make('price_usd')
                    ->label('Цена')
                    ->formatStateUsing(fn ($state, Plan $record): string => $record->price_uzs !== null
                        ? number_format($record->price_uzs, 0, '', ' ').' сум'
                        : '$'.number_format((float) $state, 2))
                    ->description(fn (Plan $record): string => "за {$record->period_days} дн."),

                TextColumn::make('active_count')
                    ->label('Компаний')
                    ->badge()
                    ->color(fn ($state): string => (int) $state > 0 ? 'success' : 'gray'),

                /*
                 * Через state(), а не formatStateUsing(): у безлимитных
                 * тарифов в базе null, а форматирование null Filament
                 * пропускает — в колонке оставалась пустота вместо
                 * «без ограничений», и Premium выглядел ненастроенным.
                 */
                TextColumn::make('listings_limit')
                    ->label('Объявлений')
                    ->state(fn (Plan $record): string => $record->limitLabel($record->listings_limit)),

                TextColumn::make('contacts_limit')
                    ->label('Контактов')
                    ->state(fn (Plan $record): string => $record->limitLabel($record->contacts_limit)),

                TextColumn::make('promo_units')->label('Промо'),

                IconColumn::make('is_active')->label('Продаётся')->boolean(),
            ])
            ->defaultSort('sort')
            ->reorderable('sort')
            ->paginated(false)
            ->recordActions([EditAction::make()]);
        /*
         * Удаления нет намеренно: на тариф ссылаются подписки и платежи,
         * и его исчезновение оставило бы историю оплат без объяснения,
         * за что заплатили. Ненужный тариф выключается флагом.
         */
    }
}
