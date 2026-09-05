<?php

declare(strict_types=1);

namespace App\Filament\Resources\Tenders\Schemas;

use App\Models\Category;
use App\Models\Country;
use App\Models\Tender;
use Filament\Forms\Components\DateTimePicker;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\Textarea;
use Filament\Forms\Components\TextInput;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Schema;

class TenderForm
{
    public static function configure(Schema $schema): Schema
    {
        return $schema->components([
            Section::make('Что закупают')
                ->schema([
                    TextInput::make('title')
                        ->label('Заголовок')
                        ->required()
                        ->maxLength(190)
                        ->columnSpanFull(),

                    Textarea::make('description')
                        ->label('Описание')
                        ->rows(10)
                        ->maxLength(10000)
                        ->helperText('Предмет закупки, объёмы, требования к поставщику. Абзацы разделяйте пустой строкой')
                        ->columnSpanFull(),

                    Select::make('category_id')
                        ->label('Категория')
                        ->options(fn (): array => Category::query()
                            ->where('is_active', true)
                            ->with(['translations', 'parent.translations'])
                            ->get()
                            ->mapWithKeys(fn (Category $c): array => [
                                $c->id => $c->parent !== null
                                    ? $c->parent->name().' → '.$c->name()
                                    : $c->name(),
                            ])
                            ->sort()
                            ->all())
                        ->searchable(),

                    TextInput::make('customer')
                        ->label('Заказчик')
                        ->maxLength(190)
                        ->placeholder('ГУП «Тошкент шахар курилиш»'),
                ])->columns(2),

            Section::make('Условия')
                ->schema([
                    TextInput::make('budget')
                        ->label('Бюджет')
                        ->numeric()
                        ->minValue(0)
                        ->helperText('Пусто — «бюджет не указан»'),

                    Select::make('currency')
                        ->label('Валюта')
                        ->options(array_combine(Tender::CURRENCIES, Tender::CURRENCIES))
                        ->default('UZS')
                        ->required(),

                    DateTimePicker::make('deadline_at')
                        ->label('Приём заявок до')
                        ->seconds(false)
                        ->helperText('После этой даты тендер уходит во «Завершённые»'),

                    Select::make('country_id')
                        ->label('Страна')
                        ->options(fn (): array => Country::query()
                            ->with('translations')
                            ->orderBy('sort')
                            ->get()
                            ->mapWithKeys(fn (Country $c): array => [$c->id => $c->name()])
                            ->all())
                        ->searchable(),

                    TextInput::make('location')
                        ->label('Город / место поставки')
                        ->maxLength(190),

                    TextInput::make('source_url')
                        ->label('Ссылка на источник')
                        ->url()
                        ->maxLength(255)
                        ->helperText('Страница закупки на сайте заказчика или площадки'),
                ])->columns(3),

            Section::make('Контакты заказчика')
                ->schema([
                    TextInput::make('contact_name')->label('Контактное лицо')->maxLength(190),
                    TextInput::make('contact_phone')->label('Телефон')->tel()->maxLength(40),
                    TextInput::make('contact_email')->label('Почта')->email()->maxLength(190),
                ])->columns(3),

            Section::make('Публикация')
                ->schema([
                    Select::make('status')
                        ->label('Статус')
                        ->options(Tender::STATUSES)
                        ->default(Tender::STATUS_DRAFT)
                        ->required(),

                    DateTimePicker::make('published_at')
                        ->label('Дата публикации')
                        ->seconds(false)
                        ->default(now())
                        ->helperText('Дата в будущем — тендер появится позже сам'),
                ])->columns(2),
        ]);
    }
}
