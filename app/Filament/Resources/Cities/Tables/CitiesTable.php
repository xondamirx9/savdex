<?php

declare(strict_types=1);

namespace App\Filament\Resources\Cities\Tables;

use App\Models\City;
use App\Models\Country;
use Filament\Actions\DeleteAction;
use Filament\Actions\EditAction;
use Filament\Tables\Columns\IconColumn;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Filters\TernaryFilter;
use Filament\Tables\Table;

class CitiesTable
{
    public static function configure(Table $table): Table
    {
        return $table
            ->modifyQueryUsing(fn ($query) => $query
                ->with(['translations', 'country.translations'])
                ->withCount(['companies', 'listings']))
            ->columns([
                TextColumn::make('name')
                    ->label('Город')
                    ->state(fn (City $record): string => $record->name())
                    ->description(fn (City $record): string => $record->slug)
                    ->searchable(query: fn ($query, string $search) => $query
                        ->where('slug', 'like', "%{$search}%")
                        ->orWhereHas('translations', fn ($q) => $q->where('name', 'like', "%{$search}%"))),

                TextColumn::make('country_id')
                    ->label('Страна')
                    ->state(fn (City $record): string => $record->country->name())
                    ->sortable(),

                TextColumn::make('translations_count')
                    ->label('Переводов')
                    ->counts('translations')
                    ->badge()
                    ->color(fn ($state): string => (int) $state >= 5 ? 'success' : 'warning')
                    ->formatStateUsing(fn ($state): string => "{$state} из 5"),

                TextColumn::make('companies_count')->label('Компаний')->sortable(),

                TextColumn::make('listings_count')->label('Объявлений')->sortable(),

                TextColumn::make('sort')->label('Порядок')->sortable(),

                IconColumn::make('is_active')
                    ->label('При регистрации')
                    ->boolean(),
            ])
            ->defaultSort('sort')
            ->filters([
                /*
                 * Фильтр по стране — главный способ найти нужный город:
                 * их сотни, и листать общий список бессмысленно.
                 * Выключенные страны в фильтре тоже есть: их города
                 * никуда не делись и могут потребовать правки.
                 */
                SelectFilter::make('country_id')
                    ->label('Страна')
                    ->relationship('country', 'code', fn ($query) => $query->with('translations'))
                    ->getOptionLabelFromRecordUsing(fn (Country $record): string => $record->name())
                    ->searchable()
                    ->preload(),

                TernaryFilter::make('is_active')->label('Показывается при регистрации'),
            ])
            ->recordActions([
                EditAction::make(),

                DeleteAction::make()
                    ->disabled(fn (City $record): bool => self::held($record) !== null)
                    ->tooltip(fn (City $record): ?string => self::held($record)),
            ])
            ->toolbarActions([]);
    }

    /** Чем город удерживается от удаления, или null, если ничем. */
    private static function held(City $record): ?string
    {
        $counts = array_filter([
            'компании' => (int) ($record->companies_count ?? 0),
            'объявления' => (int) ($record->listings_count ?? 0),
        ]);

        if ($counts === []) {
            return null;
        }

        $parts = [];

        foreach ($counts as $what => $count) {
            $parts[] = "{$what} — {$count}";
        }

        return 'Удалить нельзя, на город ссылаются: '.implode(', ', $parts)
            .'. Выключите его вместо удаления.';
    }
}
