<?php

declare(strict_types=1);

namespace App\Filament\Resources\CompanyTypes\Schemas;

use App\Filament\Resources\Categories\Schemas\CategoryForm;
use Filament\Forms\Components\Repeater;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\TextInput;
use Filament\Forms\Components\Toggle;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Schema;

/**
 * Тип компании: производитель, импортёр, дистрибьютор.
 *
 * Код не редактируется после создания: он записан в карточках
 * компаний, и его смена оставила бы их с типом, которого нет.
 */
class CompanyTypeForm
{
    public static function configure(Schema $schema): Schema
    {
        return $schema->components([
            Section::make('Тип')
                ->schema([
                    TextInput::make('code')
                        ->label('Код')
                        ->required()
                        ->maxLength(30)
                        ->unique(ignoreRecord: true)
                        ->disabledOn('edit')
                        ->helperText('Латиницей, например logistics. После создания не меняется — он записан в карточках компаний'),

                    TextInput::make('sort')
                        ->label('Порядок')
                        ->numeric()
                        ->default(0)
                        ->required()
                        ->helperText('Меньше — выше в списке при выборе'),

                    Toggle::make('is_active')
                        ->label('Доступен для выбора')
                        ->default(true)
                        ->helperText('Выключенный тип исчезает из формы регистрации, но остаётся у компаний, которые его уже выбрали'),
                ])
                ->columns(3),

            Section::make('Названия на языках')
                ->description('Русское название обязательно — оно подставляется, если перевода нет.')
                ->schema([
                    Repeater::make('translations')
                        ->hiddenLabel()
                        ->relationship()
                        ->schema([
                            Select::make('locale')
                                ->label('Язык')
                                ->options(CategoryForm::LOCALES)
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
                        ->itemLabel(fn (array $state): ?string => CategoryForm::LOCALES[$state['locale'] ?? ''] ?? null),
                ]),
        ]);
    }
}
