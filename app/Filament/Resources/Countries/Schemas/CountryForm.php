<?php

declare(strict_types=1);

namespace App\Filament\Resources\Countries\Schemas;

use App\Support\Locales;
use Filament\Forms\Components\Repeater;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\TextInput;
use Filament\Forms\Components\Toggle;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Schema;

/**
 * Форма страны.
 *
 * Названия на пяти языках задаются здесь же, а не отдельным экраном:
 * страна без перевода показывается своим кодом («uz» вместо
 * «Узбекистан»), и такую забывают дозаполнить — заметно это
 * становится уже на экране регистрации.
 */
class CountryForm
{
    public static function configure(Schema $schema): Schema
    {
        return $schema->components([
            Section::make('Страна')
                ->schema([
                    TextInput::make('code')
                        ->label('Код страны')
                        ->required()
                        ->minLength(2)
                        ->maxLength(2)
                        ->unique(ignoreRecord: true)
                        // Модель всё равно приводит код к нижнему регистру
                        // при сохранении, но человек должен видеть это
                        // сразу, а не обнаруживать после сохранения
                        ->extraInputAttributes(['style' => 'text-transform: lowercase'])
                        ->helperText('Две буквы по ISO 3166-1: uz, kz, cn. Участвует в проверке ИНН'),

                    TextInput::make('phone_code')
                        ->label('Телефонный код')
                        ->required()
                        ->maxLength(8)
                        ->helperText('Со знаком плюс: +998'),

                    TextInput::make('currency_code')
                        ->label('Валюта')
                        ->required()
                        ->minLength(3)
                        ->maxLength(3)
                        ->helperText('Три буквы по ISO 4217: UZS, KZT, USD'),

                    TextInput::make('sort')
                        ->label('Порядок')
                        ->numeric()
                        ->default(0)
                        ->required()
                        ->helperText('Меньше — выше в списке. Внутри одного порядка страны идут по алфавиту'),

                    Toggle::make('is_active')
                        ->label('Показывать при регистрации')
                        ->default(true)
                        ->helperText('Выключенная страна исчезает из выбора, но у компаний, которые её уже выбрали, остаётся'),
                ])
                ->columns(2),

            Section::make('Названия на языках')
                ->description('Русское название обязательно — оно подставляется, если перевода нет.')
                ->schema([
                    Repeater::make('translations')
                        ->hiddenLabel()
                        ->relationship()
                        ->schema([
                            Select::make('locale')
                                ->label('Язык')
                                ->options(Locales::options())
                                ->required()
                                ->distinct()
                                ->disableOptionsWhenSelectedInSiblingRepeaterItems(),

                            TextInput::make('name')
                                ->label('Название')
                                ->required()
                                ->maxLength(190),
                        ])
                        ->columns(2)
                        ->defaultItems(1)
                        ->addActionLabel('Добавить язык')
                        ->itemLabel(fn (array $state): ?string => Locales::options()[$state['locale'] ?? ''] ?? null),
                ]),
        ]);
    }
}
