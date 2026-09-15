<?php

declare(strict_types=1);

namespace App\Filament\Resources\Tasks;

use App\Filament\Concerns\AuthorizesBySection;
use App\Filament\Resources\Tasks\Pages\CreateTask;
use App\Filament\Resources\Tasks\Pages\EditTask;
use App\Filament\Resources\Tasks\Pages\ListTasks;
use App\Filament\Resources\Tasks\Schemas\TaskForm;
use App\Filament\Resources\Tasks\Tables\TasksTable;
use App\Models\Crm\Task;
use App\Support\AdminScope;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Schemas\Schema;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Database\Eloquent\Model;
use UnitEnum;

/**
 * Задачи — что сделать и к какому сроку.
 *
 * Область видимости считается по исполнителю: «свои задачи» — это те,
 * что назначены тебе, а не те, что ты завёл. Список дел должен отвечать
 * на вопрос «что мне делать сегодня».
 */
class TaskResource extends Resource
{
    use AuthorizesBySection;

    protected static string $accessSection = 'tasks';

    protected static ?string $model = Task::class;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedCheckCircle;

    protected static ?string $navigationLabel = 'Задачи';

    protected static ?string $modelLabel = 'задача';

    protected static ?string $pluralModelLabel = 'задачи';

    protected static string|UnitEnum|null $navigationGroup = 'CRM';

    protected static ?int $navigationSort = 4;

    /** Счётчик — просроченные: срок, который уже прошёл, сам о себе не напомнит. */
    public static function getNavigationBadge(): ?string
    {
        $count = AdminScope::apply(Task::query(), 'tasks', 'assignee_id')
            ->open()
            ->whereNotNull('due_at')
            ->where('due_at', '<', now())
            ->count();

        return $count > 0 ? (string) $count : null;
    }

    public static function getNavigationBadgeColor(): ?string
    {
        return 'danger';
    }

    public static function getEloquentQuery(): Builder
    {
        return AdminScope::apply(parent::getEloquentQuery(), 'tasks', 'assignee_id');
    }

    public static function canView(Model $record): bool
    {
        return parent::canView($record) && AdminScope::owns('tasks', $record->assignee_id);
    }

    public static function canEdit(Model $record): bool
    {
        return parent::canEdit($record) && AdminScope::owns('tasks', $record->assignee_id);
    }

    public static function canDelete(Model $record): bool
    {
        return parent::canDelete($record) && AdminScope::owns('tasks', $record->assignee_id);
    }

    public static function form(Schema $schema): Schema
    {
        return TaskForm::configure($schema);
    }

    public static function table(Table $table): Table
    {
        return TasksTable::configure($table);
    }

    public static function getPages(): array
    {
        return [
            'index' => ListTasks::route('/'),
            'create' => CreateTask::route('/create'),
            'edit' => EditTask::route('/{record}/edit'),
        ];
    }
}
