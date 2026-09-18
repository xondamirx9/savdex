<?php

declare(strict_types=1);

namespace App\Filament\Resources\Banners\Schemas;

use App\Models\Banner;
use App\Support\ImageStore;
use App\Support\Locales;
use Filament\Forms\Components\DateTimePicker;
use Filament\Forms\Components\FileUpload;
use Filament\Forms\Components\Repeater;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\TextInput;
use Filament\Forms\Components\Toggle;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Schema;
use Livewire\Features\SupportFileUploads\TemporaryUploadedFile;

class BannerForm
{
    /**
     * Поле картинки, которая проходит через ImageStore.

     * Филамент по умолчанию кладёт на диск ровно то, что выбрали
     * в проводнике. Для баннера это плохо втройне: снимок с телефона
     * весит восемь мегабайт и грузится первым экраном главной у всех
     * посетителей сразу; в EXIF остаются координаты съёмки; а размеры
     * никто не проверял. ImageStore пересобирает файл в WebP по рамке
     * макета — тот же путь, что у логотипов и фотографий объявлений.
     *
     * @param  array{w: int, h: int, quality: int, lossless?: bool}  $size
     */
    private static function image(string $name, array $size): FileUpload
    {
        return FileUpload::make($name)
            ->image()
            ->disk('public')
            ->directory('banners')
            ->maxSize(ImageStore::MAX_SIZE_KB)
            ->acceptedFileTypes(['image/jpeg', 'image/png', 'image/webp'])
            ->saveUploadedFileUsing(
                fn (TemporaryUploadedFile $file): string => app(ImageStore::class)->store($file, 'banners', $size),
            );
    }

    public static function configure(Schema $schema): Schema
    {
        return $schema->components([
            Section::make('Что и куда')
                ->schema([
                    TextInput::make('name')
                        ->label('Название для себя')
                        ->required()
                        ->maxLength(190)
                        ->helperText('На сайте не показывается. Нужно, чтобы отличать акции в этом списке'),

                    Select::make('placement')
                        ->label('Место на сайте')
                        ->options(Banner::PLACEMENTS)
                        ->default(Banner::PLACEMENT_HOME)
                        ->required()
                        ->helperText('На одном месте одновременно висит один баннер — тот, у кого меньше «порядок»'),

                    TextInput::make('url')
                        ->label('Куда ведёт')
                        ->url()
                        ->maxLength(500)
                        ->helperText('Можно оставить пустым — тогда баннер не кликается'),

                    TextInput::make('alt')
                        ->label('Что написано на баннере')
                        ->required()
                        ->maxLength(190)
                        // Читалка экрана произносит это вместо картинки,
                        // и это же видно, если картинка не загрузилась
                        ->helperText('Текстом: «Скидка 30% на годовой тариф до 1 октября». Нужно незрячим и поисковикам'),
                ])
                ->columns(2),

            Section::make('Срок акции')
                ->description('Пустое начало — показывать сразу. Пустой конец — бессрочно. По окончании баннер исчезает сам.')
                ->schema([
                    DateTimePicker::make('starts_at')
                        ->label('Показывать с')
                        ->seconds(false)
                        ->helperText('Акцию можно завести заранее: 29 сентября на 1 октября'),

                    DateTimePicker::make('ends_at')
                        ->label('Показывать до')
                        ->seconds(false)
                        ->after('starts_at')
                        ->helperText('Снимать руками не нужно — пропадёт сам'),

                    TextInput::make('sort')
                        ->label('Порядок')
                        ->numeric()
                        ->default(0)
                        ->required()
                        ->helperText('Меньше — важнее. При совпадении места показывается он'),

                    Toggle::make('is_active')
                        ->label('Включён')
                        ->default(true)
                        ->helperText('Выключает показ, не трогая даты'),

                    Toggle::make('is_dismissible')
                        ->label('Можно закрыть крестиком')
                        ->default(true)
                        ->helperText('Закрытый вернётся через '.Banner::DISMISS_DAYS.' дня'),
                ])
                ->columns(2),

            Section::make('Картинка')
                ->description('Широкая — для компьютера, узкая — для телефона. Обе необязательно: без узкой широкая обрежется по точке фокуса.')
                ->schema([
                    self::image('image_path', ImageStore::BANNER)
                        ->label('Для компьютера')
                        ->required()
                        ->helperText('JPG, PNG или WebP до 8 МБ. Лучше широкая, например 2400×800'),

                    self::image('image_mobile_path', ImageStore::BANNER_MOBILE)
                        ->label('Для телефона')
                        // Широкий макет на узком экране красиво не
                        // обрежется никогда — отдельная картинка
                        // решает это надёжнее любой настройки обрезки
                        ->helperText('Необязательно, но с ней телефон выглядит заметно лучше. Например 1000×1200'),

                    TextInput::make('focal_x')
                        ->label('Точка фокуса по горизонтали, %')
                        ->numeric()
                        ->minValue(0)
                        ->maxValue(100)
                        ->default(50)
                        ->helperText('Что не обрезать, когда узкой картинки нет. 0 — левый край, 100 — правый'),

                    TextInput::make('focal_y')
                        ->label('Точка фокуса по вертикали, %')
                        ->numeric()
                        ->minValue(0)
                        ->maxValue(100)
                        ->default(50)
                        ->helperText('0 — верх, 100 — низ'),
                ])
                ->columns(2),

            Section::make('Картинки под отдельные языки')
                ->description('Необязательно. Текст акции обычно внутри картинки, и русская полоса на китайской версии выглядит недоделкой. Не загрузили — везде показывается основная.')
                ->collapsed()
                ->schema([
                    Repeater::make('images')
                        ->hiddenLabel()
                        ->relationship()
                        ->schema([
                            Select::make('locale')
                                ->label('Язык')
                                ->options(Locales::options())
                                ->required()
                                ->distinct()
                                ->disableOptionsWhenSelectedInSiblingRepeaterItems(),

                            self::image('image_path', ImageStore::BANNER)
                                ->label('Для компьютера')
                                ->required(),

                            self::image('image_mobile_path', ImageStore::BANNER_MOBILE)
                                ->label('Для телефона'),
                        ])
                        ->columns(3)
                        ->defaultItems(0)
                        ->addActionLabel('Добавить язык')
                        ->itemLabel(fn (array $state): ?string => Locales::options()[$state['locale'] ?? ''] ?? null),
                ]),
        ]);
    }
}
