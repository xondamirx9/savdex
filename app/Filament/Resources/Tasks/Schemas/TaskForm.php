<?php

declare(strict_types=1);

namespace App\Filament\Resources\Tasks\Schemas;

use App\Models\Crm\Deal;
use App\Models\Crm\Lead;
use App\Models\User;
use Filament\Forms\Components\DateTimePicker;
use Filament\Forms\Components\MorphToSelect;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\Textarea;
use Filament\Forms\Components\TextInput;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Schema;
use Illuminate\Support\Facades\Auth;

class TaskForm
{
    public static function configure(Schema $schema): Schema
    {
        return $schema->components([
            Section::make('Задача')
                ->schema([
                    TextInput::make('title')
                        ->label('Что сделать')
                        ->required()
                        ->maxLength(200)
                        ->columnSpanFull()
                        ->placeholder('Позвонить и уточнить объём'),

                    Select::make('assignee_id')
                        ->label('Исполнитель')
                        ->options(fn (): array => self::employees())
                        ->default(fn (): ?int => Auth::id())
                        ->searchable()
                        ->required(),

                    DateTimePicker::make('due_at')
                        ->label('Срок')
                        ->seconds(false)
                        ->displayFormat('d.m.Y H:i')
                        // Без срока задача не всплывёт ни в счётчике,
                        // ни в фильтре «горит» — и потому не всплывёт вовсе
                        ->helperText('Задача без срока не напомнит о себе'),

                    DateTimePicker::make('done_at')
                        ->label('Выполнена')
                        ->seconds(false)
                        ->displayFormat('d.m.Y H:i')
                        ->placeholder('ещё нет'),
                ])
                ->columns(3),

            Section::make('К чему относится')
                ->description('Необязательно: бывают задачи сами по себе')
                ->schema([
                    MorphToSelect::make('subject')
                        ->label('Связана с')
                        ->types([
                            MorphToSelect\Type::make(Lead::class)
                                ->label('Лид')
                                ->titleAttribute('title'),
                            MorphToSelect\Type::make(Deal::class)
                                ->label('Сделка')
                                ->titleAttribute('title'),
                        ])
                        ->searchable(),
                ]),

            Section::make('Подробности')
                ->schema([
                    Textarea::make('description')
                        ->label('Что именно')
                        ->rows(4)
                        ->columnSpanFull(),
                ]),
        ]);
    }

    /** @return array<int, string> */
    private static function employees(): array
    {
        return User::query()
            ->where('is_admin', true)
            ->where('status', 'active')
            ->orderBy('name')
            ->get(['id', 'name', 'admin_role', 'is_admin', 'admin_permissions'])
            ->filter(fn (User $u): bool => $u->hasAdminAbility('tasks.view'))
            ->pluck('name', 'id')
            ->all();
    }
}
