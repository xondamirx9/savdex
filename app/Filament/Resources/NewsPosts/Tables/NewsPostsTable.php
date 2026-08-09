<?php

declare(strict_types=1);

namespace App\Filament\Resources\NewsPosts\Tables;

use App\Models\NewsPost;
use Filament\Actions\Action;
use Filament\Actions\BulkActionGroup;
use Filament\Actions\DeleteAction;
use Filament\Actions\DeleteBulkAction;
use Filament\Actions\EditAction;
use Filament\Notifications\Notification;
use Filament\Tables\Columns\ImageColumn;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Filters\TernaryFilter;
use Filament\Tables\Table;

class NewsPostsTable
{
    public static function configure(Table $table): Table
    {
        return $table
            ->columns([
                ImageColumn::make('image_path')
                    ->label('')
                    ->height(40)
                    ->width(64)
                    ->defaultImageUrl(null)
                    ->toggleable(),

                TextColumn::make('title')
                    ->label('Заголовок')
                    ->searchable()
                    ->wrap()
                    ->description(fn (NewsPost $record): string => $record->excerpt)
                    ->limit(70),

                TextColumn::make('category')
                    ->label('Рубрика')
                    ->badge()
                    ->searchable(),

                TextColumn::make('is_published')
                    ->label('Статус')
                    ->badge()
                    // Три состояния, а не два: «опубликована» и «выйдет
                    // 5 августа» — разные вещи, и путать их нельзя
                    ->state(function (NewsPost $record): string {
                        if (! $record->is_published) {
                            return 'Черновик';
                        }

                        return $record->published_at?->isFuture()
                            ? 'Выйдет '.$record->published_at->translatedFormat('d.m.Y')
                            : 'Опубликована';
                    })
                    ->color(fn (NewsPost $record): string => match (true) {
                        ! $record->is_published => 'gray',
                        (bool) $record->published_at?->isFuture() => 'warning',
                        default => 'success',
                    }),

                TextColumn::make('published_at')
                    ->label('Дата')
                    ->dateTime('d.m.Y')
                    ->sortable()
                    ->placeholder('—'),
            ])
            ->defaultSort('published_at', 'desc')
            ->filters([
                SelectFilter::make('category')
                    ->label('Рубрика')
                    ->options(NewsPost::CATEGORIES),

                TernaryFilter::make('is_published')->label('Опубликована'),
            ])
            ->recordActions([
                Action::make('preview')
                    ->label('Открыть')
                    ->icon('heroicon-o-arrow-top-right-on-square')
                    ->url(fn (NewsPost $record): string => url("/news/{$record->slug}"))
                    ->openUrlInNewTab()
                    ->visible(fn (NewsPost $record): bool => $record->is_published),

                Action::make('togglePublish')
                    ->label(fn (NewsPost $record): string => $record->is_published ? 'Снять' : 'Опубликовать')
                    ->icon('heroicon-o-eye')
                    ->color(fn (NewsPost $record): string => $record->is_published ? 'gray' : 'success')
                    ->requiresConfirmation()
                    ->action(function (NewsPost $record): void {
                        $record->forceFill([
                            'is_published' => ! $record->is_published,
                            'published_at' => $record->published_at ?? now(),
                        ])->save();

                        Notification::make()
                            ->title($record->is_published ? 'Новость опубликована' : 'Новость снята')
                            ->success()
                            ->send();
                    }),

                EditAction::make(),
                DeleteAction::make(),
            ])
            ->toolbarActions([
                BulkActionGroup::make([
                    DeleteBulkAction::make(),
                ]),
            ])
            ->emptyStateHeading('Новостей нет')
            ->emptyStateDescription('Новости появляются в ленте на сайте и в блоке на главной странице.');
    }
}
