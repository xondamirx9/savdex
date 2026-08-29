<?php

declare(strict_types=1);

namespace App\Filament\Resources\Listings\Schemas;

use App\Models\Category;
use App\Models\City;
use App\Models\Listing;
use Filament\Forms\Components\DateTimePicker;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\Textarea;
use Filament\Forms\Components\TextInput;
use Filament\Forms\Components\Toggle;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Schema;

/**
 * Карточка объявления в админке.
 *
 * Модератор здесь не столько правит, сколько читает: заголовок,
 * описание и цену — то, из-за чего объявление одобряют или отклоняют.
 * Мелкую правку (опечатка в заголовке, цена не в той валюте) сделать
 * можно: отклонять объявление ради запятой значит терять и время
 * модератора, и терпение продавца.
 *
 * Смены статуса в форме нет. Одобрение и отказ уходят уведомлением
 * владельцу, отказ требует причины — это действия в списке, а не
 * выпадающий список рядом с ценой.
 */
class ListingForm
{
    private const CURRENCIES = ['UZS' => 'сум', 'USD' => 'доллар'];

    public static function configure(Schema $schema): Schema
    {
        return $schema->components([
            Section::make('Что предлагают')
                ->schema([
                    Select::make('type')
                        ->label('Тип')
                        ->options([
                            Listing::TYPE_SUPPLY => 'Предложение',
                            Listing::TYPE_DEMAND => 'Запрос на закупку',
                        ])
                        ->required(),

                    Select::make('category_id')
                        ->label('Категория')
                        /*
                         * Разделы верхнего уровня тоже в списке.
                         * Отбор только подкатегорий выглядел аккуратнее,
                         * но объявление, стоящее на разделе, при таком
                         * списке теряло категорию молча: значения нет
                         * среди вариантов — Filament обнуляет поле.
                         */
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
                        ->searchable()
                        ->required(),

                    TextInput::make('title')
                        ->label('Заголовок')
                        ->required()
                        ->minLength(10)
                        ->maxLength(90)
                        ->columnSpanFull(),

                    Textarea::make('description')
                        ->label('Описание')
                        ->required()
                        ->minLength(30)
                        ->maxLength(5000)
                        ->rows(8)
                        ->columnSpanFull(),
                ])
                ->columnSpanFull()
                ->columns(2),

            Section::make('Цена и условия')
                ->schema([
                    Toggle::make('price_negotiable')
                        ->label('Цена договорная')
                        ->live()
                        ->columnSpanFull(),

                    TextInput::make('price')
                        ->label('Цена')
                        ->numeric()
                        ->minValue(0)
                        // Пустая цена допустима только вместе с отметкой
                        // «договорная» — иначе на витрине пустое место
                        ->required(fn ($get): bool => ! $get('price_negotiable'))
                        ->disabled(fn ($get): bool => (bool) $get('price_negotiable')),

                    TextInput::make('bundle_price')
                        ->label('Цена за весь комплект')
                        ->numeric()
                        ->minValue(0)
                        ->helperText('Необязательно: для товаров, продающихся набором'),

                    Select::make('currency')
                        ->label('Валюта')
                        ->options(self::CURRENCIES)
                        ->required()
                        ->default('UZS'),

                    TextInput::make('unit')->label('Единица')->maxLength(20)->placeholder('шт, тонна, м³'),

                    TextInput::make('min_order')->label('Минимальный заказ')->numeric()->minValue(0),

                    Textarea::make('delivery_terms')->label('Условия поставки')->rows(3)->maxLength(500),

                    Textarea::make('payment_terms')->label('Условия оплаты')->rows(3)->maxLength(500),
                ])
                ->columnSpanFull()
                ->columns(4),

            Section::make('Публикация')
                ->schema([
                    Select::make('city_id')
                        ->label('Город')
                        ->options(fn (): array => City::query()
                            ->where('is_active', true)
                            ->with('translations')
                            ->get()
                            ->mapWithKeys(fn (City $c): array => [$c->id => $c->name()])
                            ->all())
                        ->searchable(),

                    DateTimePicker::make('expires_at')
                        ->label('Действует до')
                        ->seconds(false)
                        ->helperText('После этой даты объявление уходит в «истёкшие»'),

                    Textarea::make('moderation_note')
                        ->label('Заметка модерации')
                        ->rows(3)
                        ->columnSpanFull()
                        // Заполняется отказом и видна владельцу. Поправить
                        // можно, стирать не стоит: без причины человек
                        // присылает то же самое повторно
                        ->helperText('Текст виден владельцу объявления. Заполняется при отказе.'),
                ])
                ->columnSpanFull()
                ->columns(2),
        ]);
    }
}
