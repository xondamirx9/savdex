<?php

declare(strict_types=1);

namespace App\Filament\Resources\Tasks\Tables;

use App\Models\Crm\Task;
use App\Support\AdminAccess;
use Filament\Actions\Action;
use Filament\Actions\BulkActionGroup;
use Filament\Actions\DeleteAction;
use Filament\Actions\DeleteBulkAction;
use Filament\Actions\EditAction;
use Filament\Notifications\Notification;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\Filter;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Support\Facades\Auth;

/**
 * Задачи: что горит и что на сегодня.
 *
 * По умолчанию видно только невыполненные и сортировка по сроку:
 * список дел отвечает на вопрос «что мне делать сейчас», а не служит
 * архивом сделанного.
 */
class TasksTable
{
    public static function configure(Table $table): Table
    {
        return $table
            ->modifyQueryUsing(fn (Builder $query): Builder => $query->with(['assignee', 'subject']))
            ->defaultSort('due_at')
            ->columns([
                TextColumn::make('title')
                    ->label('Что сделать')
                    ->searchable()
                    ->wrap()
                    ->limit(70)
                    ->description(fn (Task $r): ?string => $r->subject?->title)
                    // Выполненное видно зачёркнутым цветом, а не пропадает:
                    // «я это уже делал» — частый и законный вопрос
                    ->color(fn (Task $r): string => $r->isDone() ? 'gray' : 'primary'),

                TextColumn::make('due_at')
                    ->label('Срок')
                    ->dateTime('d.m.Y H:i')
                    ->sortable()
                    ->placeholder('без срока')
                    ->color(fn (Task $r): string => $r->isOverdue() ? 'danger' : 'gray')
                    ->description(fn (Task $r): ?string => $r->isOverdue() ? 'просрочена' : null),

                TextColumn::make('assignee.name')
                    ->label('Исполнитель')
                    ->sortable()
                    ->placeholder('—'),

                TextColumn::make('done_at')
                    ->label('Выполнена')
                    ->dateTime('d.m.Y H:i')
                    ->placeholder('—')
                    ->toggleable(),
            ])
            ->filters([
                Filter::make('open')
                    ->label('Только невыполненные')
                    ->default()
                    ->query(fn (Builder $query): Builder => $query->open()),

                Filter::make('overdue')
                    ->label('Просроченные')
                    ->query(fn (Builder $query): Builder => $query->open()
                        ->whereNotNull('due_at')
                        ->where('due_at', '<', now())),

                Filter::make('today')
                    ->label('На сегодня')
                    ->query(fn (Builder $query): Builder => $query->open()->whereDate('due_at', today())),

                Filter::make('mine')
                    ->label('Мои')
                    ->query(fn (Builder $query): Builder => $query->where('assignee_id', Auth::id())),
            ])
            ->recordActions([
                /*
                 * Отметка о выполнении одной кнопкой.
                 *
                 * Открывать форму ради одной галочки никто не станет, и
                 * список задач перестанет отражать действительность.
                 */
                Action::make('done')
                    ->label(fn (Task $r): string => $r->isDone() ? 'Вернуть в работу' : 'Выполнена')
                    ->icon(fn (Task $r): string => $r->isDone() ? 'heroicon-o-arrow-uturn-left' : 'heroicon-o-check')
                    ->color(fn (Task $r): string => $r->isDone() ? 'gray' : 'success')
                    ->visible(fn (): bool => AdminAccess::allows('tasks.edit'))
                    ->action(function (Task $record): void {
                        $record->forceFill([
                            'done_at' => $record->isDone() ? null : now(),
                        ])->save();

                        Notification::make()
                            ->title($record->isDone() ? 'Задача выполнена' : 'Задача снова в работе')
                            ->success()
                            ->send();
                    }),

                EditAction::make(),
                DeleteAction::make(),
            ])
            ->toolbarActions([
                BulkActionGroup::make([
                    DeleteBulkAction::make()
                        ->visible(fn (): bool => AdminAccess::allows('tasks.delete')),
                ]),
            ])
            ->emptyStateHeading('Задач нет')
            ->emptyStateDescription('Задача — это что сделать и к какому сроку. Её можно привязать к лиду или сделке.');
    }
}
