<?php

declare(strict_types=1);

namespace App\Filament\Resources\Categories\Tables;

use App\Models\Category;
use Filament\Actions\BulkActionGroup;
use Filament\Actions\DeleteAction;
use Filament\Actions\DeleteBulkAction;
use Filament\Actions\EditAction;
use Filament\Tables\Columns\IconColumn;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Filters\TernaryFilter;
use Filament\Tables\Table;

class CategoriesTable
{
    public static function configure(Table $table): Table
    {
        return $table
            /*
             * Связи грузятся заранее: в проекте отключена ленивая загрузка,
             * а колонки обращаются к parent и translations. Без этого
             * таблица падает с LazyLoadingViolationException — и это
             * лучше, чем молча выполнить N+1 запросов на каждую строку.
             */
            ->modifyQueryUsing(fn ($query) => $query->with(['parent.translations', 'translations']))
            ->columns([
                TextColumn::make('name')
                    ->label('Название')
                    ->state(fn (Category $record): string => $record->name())
                    ->description(fn (Category $record): string => $record->slug)
                    ->searchable(query: fn ($query, string $search) => $query
                        ->where('slug', 'like', "%{$search}%")
                        ->orWhereHas('translations', fn ($q) => $q->where('name', 'like', "%{$search}%"))),

                TextColumn::make('parent_id')
                    ->label('Раздел')
                    ->state(fn (Category $record): string => $record->parent?->name() ?? '— верхний уровень')
                    ->sortable(),

                TextColumn::make('translations_count')
                    ->label('Переводов')
                    ->counts('translations')
                    ->badge()
                    // Меньше пяти — на каком-то языке категория показывается
                    // слагом. Цвет заметнее подписи в длинном списке
                    ->color(fn ($state): string => (int) $state >= 5 ? 'success' : 'warning')
                    ->formatStateUsing(fn ($state): string => "{$state} из 5"),

                TextColumn::make('listings_count')
                    ->label('Объявлений')
                    ->counts('listings')
                    ->sortable(),

                TextColumn::make('sort')
                    ->label('Порядок')
                    ->sortable(),

                IconColumn::make('is_active')
                    ->label('Активна')
                    ->boolean(),
            ])
            ->defaultSort('sort')
            ->filters([
                SelectFilter::make('parent_id')
                    ->label('Раздел')
                    ->relationship('parent', 'slug'),

                TernaryFilter::make('is_active')->label('Активна'),
            ])
            ->recordActions([
                EditAction::make(),
                DeleteAction::make(),
            ])
            ->toolbarActions([
                BulkActionGroup::make([
                    DeleteBulkAction::make(),
                ]),
            ]);
    }
}
