<?php

declare(strict_types=1);

namespace App\Filament\Resources\Pages\Schemas;

use Filament\Forms\Components\Repeater;
use Filament\Forms\Components\Textarea;
use Filament\Forms\Components\TextInput;
use Filament\Forms\Components\Toggle;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Schema;

/**
 * Страница сайта: «О нас», «Контакты», «Помощь», правила.
 *
 * Ключ отделён от адреса: страница может переехать на другой URL,
 * а ссылки в коде обращаются к ней по ключу и не ломаются.
 */
class PageForm
{
    public static function configure(Schema $schema): Schema
    {
        return $schema->components([
            Section::make('Страница')
                ->schema([
                    TextInput::make('title')
                        ->label('Заголовок')
                        ->required()
                        ->maxLength(190),

                    TextInput::make('key')
                        ->label('Ключ')
                        ->required()
                        ->unique(ignoreRecord: true)
                        ->disabledOn('edit')
                        ->helperText('По нему на страницу ссылается код. После создания не меняется'),

                    TextInput::make('slug')
                        ->label('Адрес')
                        ->required()
                        ->unique(ignoreRecord: true)
                        ->helperText('Часть ссылки на сайте'),

                    Toggle::make('is_published')
                        ->label('Опубликована')
                        ->default(true),
                ])
                ->columns(2),

            Section::make('Содержание')
                ->schema([
                    Textarea::make('excerpt')
                        ->label('Краткое описание')
                        ->rows(2)
                        ->maxLength(500),

                    Textarea::make('body')
                        ->label('Текст')
                        ->rows(14)
                        ->helperText('Абзацы разделяйте пустой строкой'),
                ]),

            Section::make('Вопросы и ответы')
                ->description('Показываются под текстом страницы. Нужны в основном разделу «Помощь».')
                ->schema([
                    Repeater::make('faq')
                        ->hiddenLabel()
                        ->relationship()
                        ->schema([
                            TextInput::make('question')
                                ->label('Вопрос')
                                ->required()
                                ->maxLength(190),

                            Textarea::make('answer')
                                ->label('Ответ')
                                ->required()
                                ->rows(3),
                        ])
                        ->defaultItems(0)
                        ->reorderable()
                        ->orderColumn('sort')
                        ->collapsed()
                        ->addActionLabel('Добавить вопрос')
                        ->itemLabel(fn (array $state): ?string => $state['question'] ?? null),
                ])
                ->collapsible(),

            Section::make('Для поисковиков')
                ->schema([
                    TextInput::make('meta_title')
                        ->label('Заголовок в поиске')
                        ->maxLength(190)
                        ->helperText('Пусто — возьмём заголовок страницы'),

                    Textarea::make('meta_description')
                        ->label('Описание в поиске')
                        ->rows(2)
                        ->maxLength(300)
                        ->helperText('Пусто — возьмём краткое описание'),
                ])
                ->collapsed(),
        ]);
    }
}
