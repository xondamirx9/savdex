<?php

declare(strict_types=1);

namespace App\Filament\Resources\Plans\Schemas;

use Filament\Forms\Components\TextInput;
use Filament\Forms\Components\Toggle;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Schema;

/**
 * Тариф: цена, сроки, лимиты, возможности.
 *
 * Цена задаётся в долларах и пересчитывается по курсу ЦБ — при
 * скачке курса не нужно править каждый тариф руками. Поле в сумах
 * перекрывает расчёт, когда витринную цену зафиксировали.
 */
class PlanForm
{
    public static function configure(Schema $schema): Schema
    {
        return $schema->components([
            Section::make('Тариф')
                ->schema([
                    TextInput::make('code')
                        ->label('Код')
                        ->required()
                        ->maxLength(30)
                        ->unique(ignoreRecord: true)
                        ->disabledOn('edit')
                        ->helperText('Латиницей. После создания не меняется — на код ссылаются подписки и код приложения'),

                    TextInput::make('name')->label('Название')->required()->maxLength(60),

                    TextInput::make('sort')->label('Порядок')->numeric()->default(0)->required(),
                ])
                ->columns(3),

            Section::make('Цена и сроки')
                ->schema([
                    TextInput::make('price_usd')
                        ->label('Цена, $')
                        ->numeric()
                        ->required()
                        ->default(0)
                        ->helperText('Пересчитывается в сумы по курсу ЦБ'),

                    TextInput::make('price_uzs')
                        ->label('Цена в сумах')
                        ->numeric()
                        ->helperText('Заполните, только если цену зафиксировали — тогда курс не применяется'),

                    TextInput::make('period_days')
                        ->label('Период, дней')
                        ->numeric()
                        ->required()
                        ->default(30)
                        ->helperText('Сколько действует одна оплата'),

                    TextInput::make('listing_days')
                        ->label('Жизнь объявления, дней')
                        ->numeric()
                        ->required()
                        ->default(30),
                ])
                ->columns(4),

            Section::make('Лимиты')
                ->description('Пустое поле означает «без ограничений», а не ноль.')
                ->schema([
                    TextInput::make('listings_limit')
                        ->label('Объявлений')
                        ->numeric()
                        ->placeholder('без ограничений'),

                    TextInput::make('contacts_limit')
                        ->label('Раскрытий контактов в период')
                        ->numeric()
                        ->placeholder('без ограничений')
                        ->helperText('Сверх лимита списываются кредиты'),

                    TextInput::make('promo_units')
                        ->label('Промо-единиц')
                        ->numeric()
                        ->required()
                        ->default(0)
                        ->helperText('Начисляются при активации тарифа'),

                    TextInput::make('verification_days')
                        ->label('Проверка документов, дней')
                        ->numeric()
                        ->required()
                        ->default(5),
                ])
                ->columns(4),

            Section::make('Возможности')
                ->schema([
                    Toggle::make('advanced_analytics')->label('Расширенная аналитика'),
                    Toggle::make('sees_interested_names')->label('Видит, кто интересуется'),
                    Toggle::make('has_microsite')->label('Микросайт компании'),
                    Toggle::make('is_active')
                        ->label('Продаётся')
                        ->default(true)
                        ->helperText('Выключенный тариф исчезает с витрины, но у купивших продолжает действовать'),
                ])
                ->columns(4),
        ]);
    }
}
