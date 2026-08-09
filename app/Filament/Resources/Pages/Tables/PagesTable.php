<?php

declare(strict_types=1);

namespace App\Filament\Resources\Pages\Tables;

use App\Models\Page;
use Filament\Actions\Action;
use Filament\Actions\EditAction;
use Filament\Tables\Columns\IconColumn;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Table;

class PagesTable
{
    public static function configure(Table $table): Table
    {
        return $table
            ->columns([
                TextColumn::make('title')
                    ->label('Страница')
                    ->searchable()
                    ->description(fn (Page $record): ?string => $record->excerpt),

                TextColumn::make('key')
                    ->label('Ключ')
                    ->badge()
                    ->color('gray'),

                TextColumn::make('faq_count')
                    ->label('Вопросов')
                    ->counts('faq')
                    ->placeholder('—'),

                IconColumn::make('is_published')
                    ->label('Опубликована')
                    ->boolean(),
            ])
            ->defaultSort('sort')
            ->reorderable('sort')
            ->paginated(false)
            ->recordActions([
                Action::make('preview')
                    ->label('Открыть')
                    ->icon('heroicon-o-arrow-top-right-on-square')
                    ->url(fn (Page $record): string => url("/about#{$record->key}"))
                    ->openUrlInNewTab(),

                EditAction::make(),
            ]);
    }
}
