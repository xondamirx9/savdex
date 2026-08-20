<?php

declare(strict_types=1);

namespace App\Filament\Resources\Settings\Tables;

use App\Models\Setting;
use Filament\Actions\EditAction;
use Filament\Tables\Columns\ImageColumn;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Table;

class SettingsTable
{
    public static function configure(Table $table): Table
    {
        return $table
            ->columns([
                TextColumn::make('label')
                    ->label('Настройка')
                    ->searchable()
                    ->description(fn (Setting $record): string => $record->key),

                // Картинку показываем картинкой: путь вида
                // «appearance/01K2.jpg» ничего не говорит о том,
                // что стоит на витрине
                ImageColumn::make('value')
                    ->label('Значение')
                    ->disk('public')
                    ->height(44)
                    ->visible(fn (): bool => true)
                    ->getStateUsing(fn (Setting $record): ?string => $record->type === 'image' ? $record->value : null),

                TextColumn::make('value')
                    ->label('Значение')
                    ->state(function (Setting $record): string {
                        $value = $record->value;

                        return match (true) {
                            $record->type === 'image' => blank($value) ? 'не задано' : 'загружено',
                            is_bool($value) => $value ? 'да' : 'нет',
                            is_array($value) => implode(', ', $value),
                            blank($value) => '—',
                            default => (string) $value,
                        };
                    })
                    ->wrap()
                    ->limit(80),

                TextColumn::make('group')
                    ->label('Раздел')
                    ->badge()
                    ->formatStateUsing(fn (string $state): string => Setting::GROUPS[$state] ?? $state),
            ])
            ->defaultGroup('group')
            ->defaultSort('sort')
            ->paginated(false)
            ->filters([
                SelectFilter::make('group')
                    ->label('Раздел')
                    ->options(Setting::GROUPS),
            ])
            ->recordActions([
                EditAction::make(),
            ]);
    }
}
