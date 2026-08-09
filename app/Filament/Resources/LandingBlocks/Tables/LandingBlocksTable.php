<?php

declare(strict_types=1);

namespace App\Filament\Resources\LandingBlocks\Tables;

use App\Models\LandingBlock;
use Filament\Actions\EditAction;
use Filament\Tables\Columns\IconColumn;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Table;

class LandingBlocksTable
{
    public static function configure(Table $table): Table
    {
        return $table
            ->columns([
                TextColumn::make('name')
                    ->label('Блок')
                    ->description(fn (LandingBlock $record): ?string => $record->heading),

                TextColumn::make('key')
                    ->label('Ключ')
                    ->badge()
                    ->color('gray'),

                IconColumn::make('is_visible')
                    ->label('Виден')
                    ->boolean(),

                TextColumn::make('sort')
                    ->label('Порядок')
                    ->sortable(),
            ])
            ->defaultSort('sort')
            // Перетаскивание вместо ручного ввода чисел: порядок блоков
            // меняют часто, и вводить цифры для семи строк — мучение
            ->reorderable('sort')
            ->paginated(false)
            ->recordActions([
                EditAction::make(),
            ])
            ->emptyStateHeading('Блоков нет');
    }
}
