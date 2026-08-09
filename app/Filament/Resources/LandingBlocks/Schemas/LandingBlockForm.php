<?php

declare(strict_types=1);

namespace App\Filament\Resources\LandingBlocks\Schemas;

use Filament\Forms\Components\Textarea;
use Filament\Forms\Components\TextInput;
use Filament\Forms\Components\Toggle;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Schema;

/**
 * Блок главной страницы (§6.5 ТЗ).
 *
 * Ключ не редактируется: по нему фронт понимает, что рисовать.
 * Меняются тексты, порядок и видимость — то, ради чего заказчик
 * и просил вынести блоки в админку.
 */
class LandingBlockForm
{
    public static function configure(Schema $schema): Schema
    {
        return $schema->components([
            Section::make('Блок')
                ->schema([
                    TextInput::make('name')
                        ->label('Название блока')
                        ->required()
                        ->helperText('Видно только здесь — чтобы отличать блоки друг от друга'),

                    TextInput::make('key')
                        ->label('Ключ')
                        ->required()
                        ->disabledOn('edit')
                        ->helperText('По нему страница понимает, какой блок рисовать. После создания не меняется'),
                ])
                ->columns(2),

            Section::make('Тексты')
                ->description('Пустое поле — блок нарисует значение по умолчанию из вёрстки.')
                ->schema([
                    TextInput::make('eyebrow')
                        ->label('Надстрочная метка')
                        ->maxLength(120)
                        ->placeholder('B2B-площадка Узбекистана'),

                    TextInput::make('heading')
                        ->label('Заголовок')
                        ->maxLength(190),

                    Textarea::make('subheading')
                        ->label('Подзаголовок')
                        ->rows(3)
                        ->maxLength(500),
                ]),

            Section::make('Показ')
                ->schema([
                    Toggle::make('is_visible')
                        ->label('Показывать на главной')
                        ->default(true),

                    TextInput::make('sort')
                        ->label('Порядок')
                        ->numeric()
                        ->default(0)
                        ->required()
                        ->helperText('Меньше — выше на странице'),
                ])
                ->columns(2),
        ]);
    }
}
