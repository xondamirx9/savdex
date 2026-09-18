<?php

declare(strict_types=1);

namespace App\Filament\Resources\Categories\Schemas;

use App\Models\Category;
use App\Support\Locales;
use Filament\Forms\Components\Repeater;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\TextInput;
use Filament\Forms\Components\Toggle;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Schema;

/**
 * Форма категории.
 *
 * Названия на пяти языках задаются здесь же, а не отдельным экраном:
 * категория без перевода отображается своим слагом, и такую забывают
 * дозаполнить — заметно это становится уже на витрине.
 */
class CategoryForm
{
    public static function configure(Schema $schema): Schema
    {
        return $schema->components([
            Section::make('Категория')
                ->schema([
                    Select::make('parent_id')
                        ->label('Родительская категория')
                        ->relationship(
                            'parent',
                            'slug',
                            // Подкатегорию нельзя вложить в подкатегорию:
                            // дерево ровно на два уровня, третий сломает
                            // и фильтры каталога, и мастер объявления
                            // Переводы сразу: ленивую загрузку проект
                            // запрещает, а подпись строится из них
                            fn ($query) => $query->whereNull('parent_id')->with('translations'),
                        )
                        ->getOptionLabelFromRecordUsing(fn (Category $record): string => $record->name())
                        ->searchable()
                        ->preload()
                        ->helperText('Пусто — это раздел верхнего уровня'),

                    TextInput::make('slug')
                        ->label('Адрес (slug)')
                        ->required()
                        ->maxLength(190)
                        ->unique(ignoreRecord: true)
                        ->helperText('Латиницей, участвует в адресе страницы'),

                    TextInput::make('icon')
                        ->label('Иконка')
                        ->maxLength(64)
                        ->helperText('Имя иконки Lucide, например package'),

                    TextInput::make('sort')
                        ->label('Порядок')
                        ->numeric()
                        ->default(0)
                        ->required()
                        ->helperText('Меньше — выше в списке'),

                    Toggle::make('is_active')
                        ->label('Активна')
                        ->default(true)
                        ->helperText('Выключенная скрыта из каталога и мастера объявлений'),
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
