<?php

declare(strict_types=1);

namespace App\Filament\Resources\Settings\Tables;

use App\Models\Setting;
use Filament\Actions\EditAction;
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

                TextColumn::make('value')
                    ->label('Значение')
                    ->state(function (Setting $record): string {
                        $value = $record->value;

                        return match (true) {
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
