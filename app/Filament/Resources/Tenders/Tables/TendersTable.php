<?php

declare(strict_types=1);

namespace App\Filament\Resources\Tenders\Tables;

use App\Filament\Imports\TenderImporter;
use App\Models\Tender;
use Filament\Actions\Action;
use Filament\Actions\BulkAction;
use Filament\Actions\BulkActionGroup;
use Filament\Actions\CreateAction;
use Filament\Actions\DeleteAction;
use Filament\Actions\DeleteBulkAction;
use Filament\Actions\EditAction;
use Filament\Actions\ImportAction;
use Filament\Notifications\Notification;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Collection;

class TendersTable
{
    public static function configure(Table $table): Table
    {
        return $table
            ->modifyQueryUsing(fn ($query) => $query->with(['category.translations', 'country.translations']))
            ->columns([
                TextColumn::make('title')
                    ->label('Тендер')
                    ->searchable()
                    ->wrap()
                    ->limit(80)
                    ->description(fn (Tender $t): ?string => $t->customer),

                TextColumn::make('category.slug')
                    ->label('Категория')
                    ->formatStateUsing(fn (Tender $t): string => $t->category?->name() ?? '—')
                    ->placeholder('—'),

                TextColumn::make('budget')
                    ->label('Бюджет')
                    ->formatStateUsing(fn (Tender $t): string => $t->budget !== null
                        ? number_format((float) $t->budget, 0, ',', ' ').' '.$t->currency
                        : '—')
                    ->placeholder('—')
                    ->sortable(),

                TextColumn::make('deadline_at')
                    ->label('Приём до')
                    ->dateTime('d.m.Y')
                    ->placeholder('—')
                    ->sortable()
                    ->color(fn (Tender $t): ?string => $t->isClosed() ? 'gray' : null),

                TextColumn::make('status')
                    ->label('Статус')
                    ->badge()
                    ->formatStateUsing(fn (string $state): string => Tender::STATUSES[$state] ?? $state)
                    ->color(fn (string $state): string => match ($state) {
                        Tender::STATUS_PUBLISHED => 'success',
                        Tender::STATUS_ARCHIVED => 'gray',
                        default => 'warning',
                    }),

                TextColumn::make('published_at')
                    ->label('Опубликован')
                    ->dateTime('d.m.Y')
                    ->sortable()
                    ->toggleable(),
            ])
            ->defaultSort('created_at', 'desc')
            ->filters([
                SelectFilter::make('status')->label('Статус')->options(Tender::STATUSES),
            ])
            ->headerActions([
                CreateAction::make()->label('Добавить'),

                // Массовая загрузка: файл CSV с русскими заголовками,
                // образец скачивается из окна импорта
                ImportAction::make()
                    ->label('Загрузить из файла')
                    ->importer(TenderImporter::class),
            ])
            ->recordActions([
                Action::make('preview')
                    ->label('На сайте')
                    ->icon('heroicon-o-arrow-top-right-on-square')
                    ->url(fn (Tender $t): string => url('/tenders/'.$t->slug))
                    ->openUrlInNewTab()
                    ->visible(fn (Tender $t): bool => $t->status === Tender::STATUS_PUBLISHED && filled($t->slug)),

                Action::make('publish')
                    ->label('Опубликовать')
                    ->icon('heroicon-o-check')
                    ->color('success')
                    ->visible(fn (Tender $t): bool => $t->status !== Tender::STATUS_PUBLISHED)
                    ->action(function (Tender $t): void {
                        self::publish($t);
                        Notification::make()->title('Тендер опубликован')->success()->send();
                    }),

                EditAction::make(),
                DeleteAction::make(),
            ])
            ->toolbarActions([
                BulkActionGroup::make([
                    BulkAction::make('publishSelected')
                        ->label('Опубликовать выбранные')
                        ->icon('heroicon-o-check')
                        ->color('success')
                        ->requiresConfirmation()
                        ->action(function (Collection $records): void {
                            $records->each(fn (Tender $t) => self::publish($t));
                            Notification::make()->title('Опубликовано: '.$records->count())->success()->send();
                        })
                        ->deselectRecordsAfterCompletion(),

                    BulkAction::make('archiveSelected')
                        ->label('В архив')
                        ->icon('heroicon-o-archive-box')
                        ->color('gray')
                        ->requiresConfirmation()
                        ->action(function (Collection $records): void {
                            $records->each(fn (Tender $t) => $t->forceFill(['status' => Tender::STATUS_ARCHIVED])->save());
                            Notification::make()->title('В архиве: '.$records->count())->success()->send();
                        })
                        ->deselectRecordsAfterCompletion(),

                    DeleteBulkAction::make(),
                ]),
            ])
            ->emptyStateHeading('Тендеров пока нет')
            ->emptyStateDescription('Добавьте тендер вручную или загрузите таблицу — раздел на сайте появится сразу после публикации');
    }

    private static function publish(Tender $tender): void
    {
        $tender->forceFill([
            'status' => Tender::STATUS_PUBLISHED,
            'published_at' => $tender->published_at ?? now(),
        ])->save();
    }
}
