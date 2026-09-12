<?php

declare(strict_types=1);

namespace App\Filament\Resources\ItTasks\Schemas;

use App\Models\ItTask;
use Filament\Forms\Components\DatePicker;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\TagsInput;
use Filament\Forms\Components\Textarea;
use Filament\Forms\Components\TextInput;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Schema;

class ItTaskForm
{
    public static function configure(Schema $schema): Schema
    {
        return $schema->components([
            Section::make('Задача')
                ->schema([
                    TextInput::make('title')->label('Название')->required()->maxLength(120)->columnSpanFull(),
                    Textarea::make('description')->label('Описание')->required()->rows(10)->maxLength(8000)->columnSpanFull(),
                    Select::make('service_type')->label('Вид услуги')->options(ItTask::SERVICE_TYPES)->required(),
                    TagsInput::make('stack')->label('Стек')->placeholder('Laravel, React…'),
                ])->columns(2),

            Section::make('Условия')
                ->schema([
                    Select::make('budget_type')->label('Бюджет')->options([
                        'negotiable' => 'Договорной',
                        'fixed' => 'Фиксированный',
                        'range' => 'Диапазон',
                    ])->required(),
                    TextInput::make('budget_from')->label('От / сумма')->numeric()->minValue(0),
                    TextInput::make('budget_to')->label('До')->numeric()->minValue(0),
                    Select::make('currency')->label('Валюта')->options(array_combine(ItTask::CURRENCIES, ItTask::CURRENCIES))->required(),
                    DatePicker::make('deadline_at')->label('Срок сдачи'),
                ])->columns(3),

            Section::make('Статус')
                ->schema([
                    Select::make('status')->label('Статус')->options(ItTask::STATUSES)->required(),
                ]),
        ]);
    }
}
