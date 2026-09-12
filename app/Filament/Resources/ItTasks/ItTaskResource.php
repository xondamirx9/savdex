<?php

declare(strict_types=1);

namespace App\Filament\Resources\ItTasks;

use App\Filament\Resources\ItTasks\Pages\EditItTask;
use App\Filament\Resources\ItTasks\Pages\ListItTasks;
use App\Filament\Resources\ItTasks\Schemas\ItTaskForm;
use App\Filament\Resources\ItTasks\Tables\ItTasksTable;
use App\Models\ItTask;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Schemas\Schema;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;

/**
 * IT-задачи компаний — раздел «Данные»: просмотр, правка, снятие.
 *
 * Создаются только из кабинета компании (задача от имени заказчика),
 * поэтому страницы создания нет — как у объявлений.
 */
class ItTaskResource extends Resource
{
    protected static ?string $model = ItTask::class;

    protected static ?string $navigationLabel = 'IT-задачи';

    protected static ?string $modelLabel = 'IT-задача';

    protected static ?string $pluralModelLabel = 'IT-задачи';

    protected static string|\UnitEnum|null $navigationGroup = 'Данные';

    protected static ?int $navigationSort = 3;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedCodeBracket;

    public static function form(Schema $schema): Schema
    {
        return ItTaskForm::configure($schema);
    }

    public static function table(Table $table): Table
    {
        return ItTasksTable::configure($table);
    }

    public static function getPages(): array
    {
        return [
            'index' => ListItTasks::route('/'),
            'edit' => EditItTask::route('/{record}/edit'),
        ];
    }
}
