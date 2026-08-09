<?php

declare(strict_types=1);

namespace App\Filament\Resources\NewsPosts\Schemas;

use App\Models\NewsPost;
use Filament\Forms\Components\DateTimePicker;
use Filament\Forms\Components\FileUpload;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\Textarea;
use Filament\Forms\Components\TextInput;
use Filament\Forms\Components\Toggle;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Components\Utilities\Set;
use Filament\Schemas\Schema;

/**
 * Новость площадки.
 *
 * Текст обычный, без визуального редактора: абзацы разделяются пустой
 * строкой. Редактор с форматированием на такой длине текста добавляет
 * только способы сломать вёрстку.
 */
class NewsPostForm
{
    public static function configure(Schema $schema): Schema
    {
        return $schema->components([
            Section::make('Публикация')
                ->schema([
                    TextInput::make('title')
                        ->label('Заголовок')
                        ->required()
                        ->maxLength(190)
                        ->live(onBlur: true)
                        // Адрес подставляется из заголовка, но остаётся
                        // редактируемым: у готовых новостей его менять нельзя,
                        // иначе внешние ссылки перестанут работать
                        ->afterStateUpdated(function (Set $set, ?string $state, string $operation): void {
                            if ($operation === 'create' && filled($state)) {
                                $set('slug', NewsPost::makeSlug($state));
                            }
                        }),

                    TextInput::make('slug')
                        ->label('Адрес')
                        ->required()
                        ->unique(ignoreRecord: true)
                        ->maxLength(190)
                        ->helperText('Часть ссылки: /news/адрес. После публикации лучше не менять'),

                    Select::make('category')
                        ->label('Рубрика')
                        ->options(NewsPost::CATEGORIES)
                        ->required()
                        ->helperText('Задаёт оформление обложки, если картинки нет'),

                    TextInput::make('read_time')
                        ->label('Время чтения')
                        ->maxLength(20)
                        ->placeholder('4 мин')
                        ->helperText('Пусто — посчитаем по объёму текста'),
                ])
                ->columns(2),

            Section::make('Содержание')
                ->schema([
                    Textarea::make('excerpt')
                        ->label('Краткое описание')
                        ->required()
                        ->rows(3)
                        ->maxLength(500)
                        ->helperText('Видно в ленте новостей и в поисковой выдаче'),

                    Textarea::make('body')
                        ->label('Текст')
                        ->required()
                        ->rows(16)
                        ->helperText('Абзацы разделяйте пустой строкой'),

                    FileUpload::make('image_path')
                        ->label('Обложка')
                        ->image()
                        ->imageEditor()
                        ->directory('news')
                        ->maxSize(4096)
                        ->helperText('Необязательно: без картинки покажем градиент по рубрике. От 1200 px по ширине, до 4 МБ'),
                ]),

            Section::make('Видимость')
                ->schema([
                    Toggle::make('is_published')
                        ->label('Опубликована')
                        ->default(false)
                        ->helperText('Черновик виден только здесь'),

                    DateTimePicker::make('published_at')
                        ->label('Дата публикации')
                        ->seconds(false)
                        ->default(now())
                        // Дата в будущем работает как отложенная публикация:
                        // новость не появится на сайте раньше срока
                        ->helperText('Дата в будущем — новость появится позже сама'),

                    TextInput::make('sort')
                        ->label('Порядок')
                        ->numeric()
                        ->default(0)
                        ->helperText('Больше — выше в ленте при одинаковой дате'),
                ])
                ->columns(3),
        ]);
    }
}
