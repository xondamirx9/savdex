<?php

declare(strict_types=1);

namespace App\Filament\Resources\Contacts\Schemas;

use Filament\Forms\Components\Select;
use Filament\Forms\Components\Textarea;
use Filament\Forms\Components\TextInput;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Schema;

class ContactForm
{
    public static function configure(Schema $schema): Schema
    {
        return $schema->components([
            Section::make('Человек')
                ->schema([
                    TextInput::make('name')
                        ->label('Имя')
                        ->required()
                        ->maxLength(160),

                    TextInput::make('position')
                        ->label('Должность')
                        ->maxLength(120)
                        ->placeholder('Снабженец, директор, бухгалтер'),

                    Select::make('company_id')
                        ->label('Компания')
                        ->relationship('company', 'name')
                        ->searchable()
                        ->preload()
                        // Контакт без компании — норма: человека часто
                        // знают раньше, чем узнают, где он работает
                        ->placeholder('Пока неизвестна'),
                ])
                ->columns(3),

            Section::make('Как связаться')
                ->schema([
                    TextInput::make('phone')->label('Телефон')->tel()->maxLength(40),
                    TextInput::make('email')->label('Почта')->email()->maxLength(160),
                    TextInput::make('telegram')->label('Telegram')->maxLength(80)->prefix('@'),
                ])
                ->columns(3),

            Section::make('Заметки')
                ->schema([
                    Textarea::make('note')
                        ->label('Что важно помнить')
                        ->rows(4)
                        ->columnSpanFull()
                        ->helperText('Чем занимается, как удобнее связываться, о чём договаривались'),
                ]),
        ]);
    }
}
