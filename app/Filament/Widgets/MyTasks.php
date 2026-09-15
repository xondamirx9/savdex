<?php

declare(strict_types=1);

namespace App\Filament\Widgets;

use App\Filament\Resources\Tasks\TaskResource;
use App\Models\Crm\Task;
use App\Support\AdminAccess;
use App\Support\AdminScope;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Table;
use Filament\Widgets\TableWidget;

/**
 * Что сделать сегодня.
 *
 * Просроченные и сегодняшние вместе, просроченные первыми: срок,
 * который уже прошёл, сам о себе не напомнит. Задачи без срока сюда
 * не попадают намеренно — они не про сегодня.
 */
class MyTasks extends TableWidget
{
    protected static ?int $sort = -29;

    protected int|string|array $columnSpan = 'full';

    public static function canView(): bool
    {
        return AdminAccess::allows('tasks.view');
    }

    public function table(Table $table): Table
    {
        return $table
            ->heading('Задачи на сегодня')
            ->description('Просроченные и сегодняшние')
            ->query(
                AdminScope::apply(Task::query(), 'tasks', 'assignee_id')
                    ->open()
                    ->whereNotNull('due_at')
                    ->whereDate('due_at', '<=', today())
                    ->with(['assignee', 'subject']),
            )
            ->defaultSort('due_at')
            ->paginated([5])
            ->columns([
                TextColumn::make('title')
                    ->label('Что сделать')
                    ->wrap()
                    ->limit(70)
                    ->description(fn (Task $record): ?string => $record->subject?->title),

                TextColumn::make('due_at')
                    ->label('Срок')
                    ->dateTime('d.m.Y H:i')
                    ->color(fn (Task $record): string => $record->isOverdue() ? 'danger' : 'gray')
                    ->description(fn (Task $record): ?string => $record->isOverdue() ? 'просрочена' : null),

                TextColumn::make('assignee.name')
                    ->label('Исполнитель')
                    ->placeholder('—'),
            ])
            ->recordUrl(fn (Task $record): string => TaskResource::getUrl('edit', ['record' => $record]))
            ->emptyStateHeading('На сегодня задач нет')
            ->emptyStateDescription('Сюда попадают задачи со сроком сегодня и раньше.');
    }
}
