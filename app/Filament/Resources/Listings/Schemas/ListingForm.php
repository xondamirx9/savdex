<?php

declare(strict_types=1);

namespace App\Filament\Resources\Listings\Schemas;

use App\Models\Category;
use App\Models\City;
use App\Models\Listing;
use App\Support\Currencies;
use App\Support\Locales;
use Filament\Forms\Components\DateTimePicker;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\Textarea;
use Filament\Forms\Components\TextInput;
use Filament\Forms\Components\Toggle;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Components\Tabs;
use Filament\Schemas\Components\Tabs\Tab;
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
 *
 * Тексты — по вкладке на язык. Русский лежит в самих колонках,
 * остальные четыре — в колонках переводов (title_i18n.en и т. д.).
 * Цена, категория и прочее, что у товара одно на все языки, стоят
 * один раз: пять цен — это пять мест, где она может разойтись.
 */
class ListingForm
{
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

                ])
                ->columnSpanFull()
                ->columns(2),

            Section::make('Тексты по языкам')
                ->description('Русский обязателен. Остальные языки — по желанию: без перевода загруженное '
                    .'из Excel объявление на этом языке не показывается, написанное в кабинете — показывается по-русски.')
                ->schema([
                    Tabs::make('texts')
                        ->tabs(array_map(
                            fn (string $locale): Tab => self::textsTab($locale),
                            Locales::codes(),
                        ))
                        ->persistTabInQueryString('lang')
                        ->columnSpanFull(),
                ])
                ->columnSpanFull(),

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
                        ->options(Currencies::labels())
                        ->required()
                        ->default('UZS'),

                    TextInput::make('unit')->label('Единица')->maxLength(20)->placeholder('шт, тонна, м³'),

                    TextInput::make('min_order')->label('Минимальный заказ')->numeric()->minValue(0),
                ])
                ->columnSpanFull()
                ->columns(4),

            Section::make('Публикация')
                ->schema([
                    Select::make('city_id')
                        ->label('Город')
                        /*
                         * Со страной в подписи: городов на площадке
                         * три сотни, и «Триполи» без страны рядом —
                         * загадка, а не выбор. Как в списке категорий
                         * выше, где раздел стоит перед подкатегорией.
                         */
                        ->options(fn (): array => City::query()
                            ->where('is_active', true)
                            ->with(['translations', 'country.translations'])
                            ->orderBy('country_id')
                            ->orderBy('sort')
                            ->get()
                            ->mapWithKeys(fn (City $c): array => [
                                $c->id => $c->country?->name().' → '.$c->name(),
                            ])
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

    /**
     * Вкладка одного языка: четыре переводимых поля.
     *
     * У русского поля — обычные колонки и те же требования, что
     * в кабинете. У остальных — переводные колонки и без «обязательно»:
     * перевод может отсутствовать, это законное состояние.
     */
    private static function textsTab(string $locale): Tab
    {
        $russian = $locale === Locales::DEFAULT;
        $name = fn (string $field): string => $russian ? $field : $field.'_i18n.'.$locale;

        return Tab::make($locale)
            ->label(Locales::ALL[$locale]['label'])
            ->schema([
                TextInput::make($name('title'))
                    ->label('Заголовок')
                    ->required($russian)
                    ->minLength($russian ? 10 : null)
                    ->maxLength(Listing::MAX_LENGTH['title'])
                    ->columnSpanFull(),

                Textarea::make($name('description'))
                    ->label('Описание')
                    ->required($russian)
                    ->minLength($russian ? 30 : null)
                    ->maxLength(Listing::MAX_LENGTH['description'])
                    ->rows(8)
                    ->columnSpanFull(),

                Textarea::make($name('delivery_terms'))
                    ->label('Условия поставки')
                    ->rows(3)
                    ->maxLength(Listing::MAX_LENGTH['delivery_terms']),

                Textarea::make($name('payment_terms'))
                    ->label('Условия оплаты')
                    ->rows(3)
                    ->maxLength(Listing::MAX_LENGTH['payment_terms']),
            ])
            ->columns(2);
    }
}
