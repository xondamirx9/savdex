<?php

declare(strict_types=1);

namespace App\Filament\Resources\ItTasks\Tables;

use App\Models\ItTask;
use Filament\Actions\Action;
use Filament\Actions\BulkActionGroup;
use Filament\Actions\DeleteAction;
use Filament\Actions\DeleteBulkAction;
use Filament\Actions\EditAction;
use Filament\Notifications\Notification;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Table;

class ItTasksTable
{
    public static function configure(Table $table): Table
    {
        return $table
            ->modifyQueryUsing(fn ($query) => $query->with('company'))
            ->columns([
                TextColumn::make('title')
                    ->label('Задача')
                    ->searchable()
                    ->wrap()
                    ->limit(80)
                    ->description(fn (ItTask $t): ?string => $t->company?->name),

                TextColumn::make('service_type')
                    ->label('Вид услуги')
                    ->formatStateUsing(fn (string $state): string => ItTask::SERVICE_TYPES[$state] ?? $state),

                TextColumn::make('responses_count')->label('Откликов')->sortable(),

                TextColumn::make('status')
                    ->label('Статус')
                    ->badge()
                    ->formatStateUsing(fn (string $state): string => ItTask::STATUSES[$state] ?? $state)
                    ->color(fn (string $state): string => match ($state) {
                        ItTask::STATUS_ACTIVE => 'success',
                        default => 'gray',
                    }),

                TextColumn::make('published_at')->label('Опубликована')->dateTime('d.m.Y')->sortable(),
            ])
            ->defaultSort('created_at', 'desc')
            ->filters([
                SelectFilter::make('status')->label('Статус')->options(ItTask::STATUSES),
                SelectFilter::make('service_type')->label('Вид услуги')->options(ItTask::SERVICE_TYPES),
            ])
            ->recordActions([
                Action::make('preview')
                    ->label('На сайте')
                    ->icon('heroicon-o-arrow-top-right-on-square')
                    ->url(fn (ItTask $t): string => url('/it-services/'.$t->slug))
                    ->openUrlInNewTab()
                    ->visible(fn (ItTask $t): bool => $t->isActive() && filled($t->slug)),

                // Снятие с витрины — для спама и нарушений; заказчик
                // увидит задачу в кабинете как архивную
                Action::make('archive')
                    ->label('Снять')
                    ->icon('heroicon-o-archive-box')
                    ->color('gray')
                    ->requiresConfirmation()
                    ->visible(fn (ItTask $t): bool => $t->isActive())
                    ->action(function (ItTask $t): void {
                        $t->forceFill(['status' => ItTask::STATUS_ARCHIVED, 'closed_at' => now()])->save();
                        Notification::make()->title('Задача снята с витрины')->success()->send();
                    }),

                EditAction::make(),
                DeleteAction::make(),
            ])
            ->toolbarActions([
                BulkActionGroup::make([DeleteBulkAction::make()]),
            ])
            ->emptyStateHeading('IT-задач пока нет')
            ->emptyStateDescription('Задачи публикуют компании из кабинета — раздел «IT-задачи»');
    }
}
