<?php

declare(strict_types=1);

namespace App\Filament\Resources\Cities\Schemas;

use App\Models\Country;
use App\Support\Locales;
use Filament\Forms\Components\Repeater;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\TextInput;
use Filament\Forms\Components\Toggle;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Schema;

class CityForm
{
    public static function configure(Schema $schema): Schema
    {
        return $schema->components([
            Section::make('Город')
                ->schema([
                    Select::make('country_id')
                        ->label('Страна')
                        ->relationship('country', 'code', fn ($query) => $query->with('translations'))
                        ->getOptionLabelFromRecordUsing(fn (Country $record): string => $record->name())
                        ->required()
                        ->searchable()
                        ->preload()
                        /*
                         * Выключенные страны в списке остаются намеренно:
                         * у страны, снятой с публикации, города никуда не
                         * делись, и их надо уметь править — иначе форма
                         * города, стоящего на ней, не сохранится вовсе.
                         */
                        ->helperText('Выключенные страны тоже доступны — их города продолжают жить'),

                    TextInput::make('slug')
                        ->label('Адрес (slug)')
                        ->required()
                        ->maxLength(190)
                        ->helperText('Латиницей, участвует в адресе страницы: tashkent'),

                    TextInput::make('sort')
                        ->label('Порядок')
                        ->numeric()
                        ->default(0)
                        ->required()
                        ->helperText('Меньше — выше в списке'),

                    Toggle::make('is_active')
                        ->label('Показывать при регистрации')
                        ->default(true),
                ])
                ->columns(2),

            Section::make('Координаты')
                ->description('Необязательны. Нужны там, где город показывается на карте.')
                ->schema([
                    TextInput::make('lat')
                        ->label('Широта')
                        ->numeric()
                        ->minValue(-90)
                        ->maxValue(90)
                        ->helperText('Например 41.2995'),

                    TextInput::make('lng')
                        ->label('Долгота')
                        ->numeric()
                        ->minValue(-180)
                        ->maxValue(180)
                        ->helperText('Например 69.2401'),
                ])
                ->columns(2)
                ->collapsed(),

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
