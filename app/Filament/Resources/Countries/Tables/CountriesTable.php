<?php

declare(strict_types=1);

namespace App\Filament\Resources\Countries\Tables;

use App\Models\Country;
use Filament\Actions\DeleteAction;
use Filament\Actions\EditAction;
use Filament\Tables\Columns\IconColumn;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\TernaryFilter;
use Filament\Tables\Table;

class CountriesTable
{
    public static function configure(Table $table): Table
    {
        return $table
            /*
             * Счётчики берутся одним запросом на всю страницу, а не
             * тремя на строку: их показывают колонки, и по ним же
             * решается, можно ли удалять. В проекте отключена ленивая
             * загрузка — переводы тоже грузятся заранее.
             */
            ->modifyQueryUsing(fn ($query) => $query
                ->with('translations')
                ->withCount(['cities', 'companies', 'tenders']))
            ->columns([
                TextColumn::make('name')
                    ->label('Страна')
                    ->state(fn (Country $record): string => $record->name())
                    ->description(fn (Country $record): string => mb_strtoupper($record->code))
                    ->searchable(query: fn ($query, string $search) => $query
                        ->where('code', 'like', "%{$search}%")
                        ->orWhereHas('translations', fn ($q) => $q->where('name', 'like', "%{$search}%"))),

                TextColumn::make('phone_code')->label('Телефон'),

                TextColumn::make('currency_code')->label('Валюта'),

                TextColumn::make('translations_count')
                    ->label('Переводов')
                    ->counts('translations')
                    ->badge()
                    // Меньше пяти — на каком-то языке страна показывается
                    // кодом. Цвет заметнее подписи в длинном списке
                    ->color(fn ($state): string => (int) $state >= 5 ? 'success' : 'warning')
                    ->formatStateUsing(fn ($state): string => "{$state} из 5"),

                TextColumn::make('cities_count')->label('Городов')->sortable(),

                TextColumn::make('companies_count')->label('Компаний')->sortable(),

                TextColumn::make('sort')->label('Порядок')->sortable(),

                IconColumn::make('is_active')
                    ->label('При регистрации')
                    ->boolean(),
            ])
            ->defaultSort('sort')
            ->filters([
                TernaryFilter::make('is_active')->label('Показывается при регистрации'),
            ])
            ->recordActions([
                EditAction::make(),

                /*
                 * Удаление недоступно, пока на страну кто-то ссылается.
                 *
                 * Внешние ключи этому не мешают: города ушли бы каскадом,
                 * а у компаний и тендеров адрес молча обнулился бы. Кнопка
                 * не прячется, а гаснет с подсказкой — иначе на её месте
                 * остаётся вопрос «почему удалить нельзя» без ответа.
                 */
                DeleteAction::make()
                    ->disabled(fn (Country $record): bool => self::held($record) !== null)
                    ->tooltip(fn (Country $record): ?string => self::held($record)),
            ])
            // Массового удаления у справочника нет намеренно: записей
            // мало, а последствия ошибки велики и необратимы
            ->toolbarActions([]);
    }

    /** Чем страна удерживается от удаления, или null, если ничем. */
    private static function held(Country $record): ?string
    {
        $counts = array_filter([
            'города' => (int) ($record->cities_count ?? 0),
            'компании' => (int) ($record->companies_count ?? 0),
            'тендеры' => (int) ($record->tenders_count ?? 0),
        ]);

        if ($counts === []) {
            return null;
        }

        $parts = [];

        foreach ($counts as $what => $count) {
            $parts[] = "{$what} — {$count}";
        }

        return 'Удалить нельзя, на страну ссылаются: '.implode(', ', $parts)
            .'. Выключите её вместо удаления.';
    }
}
