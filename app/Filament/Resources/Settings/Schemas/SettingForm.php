<?php

declare(strict_types=1);

namespace App\Filament\Resources\Settings\Schemas;

use App\Models\Setting;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\Textarea;
use Filament\Forms\Components\TextInput;
use Filament\Forms\Components\Toggle;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Components\Utilities\Get;
use Filament\Schemas\Schema;

/**
 * Настройка площадки.
 *
 * Поле значения меняется под тип: для числа — числовой ввод, для флага
 * — переключатель. Один универсальный текстовый ввод приводит к тому,
 * что в числовую настройку однажды попадает «два часа».
 */
class SettingForm
{
    public static function configure(Schema $schema): Schema
    {
        return $schema->components([
            Section::make('Настройка')
                ->schema([
                    TextInput::make('label')
                        ->label('Название')
                        ->required()
                        ->maxLength(190),

                    TextInput::make('key')
                        ->label('Ключ')
                        ->required()
                        ->unique(ignoreRecord: true)
                        ->disabledOn('edit')
                        ->helperText('По нему настройка читается из кода. После создания не меняется'),

                    Select::make('group')
                        ->label('Раздел')
                        ->options(Setting::GROUPS)
                        ->default('general')
                        ->required(),

                    Select::make('type')
                        ->label('Тип значения')
                        ->options([
                            'string' => 'Строка',
                            'text' => 'Текст',
                            'number' => 'Число',
                            'bool' => 'Да / нет',
                        ])
                        ->default('string')
                        ->required()
                        ->live()
                        ->disabledOn('edit')
                        ->helperText('После создания не меняется: код ждёт значение определённого типа'),
                ])
                ->columns(2),

            Section::make('Значение')
                ->schema([
                    TextInput::make('value')
                        ->label('Значение')
                        ->visible(fn (Get $get): bool => $get('type') === 'string')
                        ->maxLength(500),

                    Textarea::make('value')
                        ->label('Значение')
                        ->visible(fn (Get $get): bool => $get('type') === 'text')
                        ->rows(4),

                    TextInput::make('value')
                        ->label('Значение')
                        ->numeric()
                        ->visible(fn (Get $get): bool => $get('type') === 'number'),

                    Toggle::make('value')
                        ->label('Включено')
                        ->visible(fn (Get $get): bool => $get('type') === 'bool'),

                    Textarea::make('description')
                        ->label('Пояснение')
                        ->rows(2)
                        ->helperText('Подсказка для того, кто будет менять настройку после вас'),
                ]),
        ]);
    }
}
