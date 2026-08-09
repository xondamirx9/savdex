<?php

declare(strict_types=1);

namespace App\Filament\Resources\CreditPacks\Schemas;

use Filament\Forms\Components\TextInput;
use Filament\Forms\Components\Toggle;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Schema;

/**
 * Пакет кредитов на раскрытие контактов.
 *
 * Цена в долларах пересчитывается по курсу ЦБ; поле в сумах
 * перекрывает расчёт, когда витринную цену зафиксировали — круглая
 * цифра продаёт лучше, чем результат умножения.
 */
class CreditPackForm
{
    public static function configure(Schema $schema): Schema
    {
        return $schema->components([
            Section::make('Пакет')
                ->schema([
                    TextInput::make('code')
                        ->label('Код')
                        ->required()
                        ->maxLength(30)
                        ->unique(ignoreRecord: true)
                        ->disabledOn('edit')
                        ->helperText('Латиницей. После создания не меняется — на него ссылаются выставленные счета'),

                    TextInput::make('name')
                        ->label('Название')
                        ->required()
                        ->maxLength(60)
                        ->helperText('То, что видит покупатель: «30 контактов»'),

                    TextInput::make('credits')
                        ->label('Кредитов в пакете')
                        ->numeric()
                        ->minValue(1)
                        ->required(),

                    TextInput::make('sort')->label('Порядок')->numeric()->default(0)->required(),
                ])
                ->columnSpanFull()
                ->columns(4),

            Section::make('Цена')
                ->schema([
                    TextInput::make('price_usd')
                        ->label('Цена, $')
                        ->numeric()
                        ->required()
                        ->helperText('Пересчитывается в сумы по курсу ЦБ'),

                    TextInput::make('price_uzs')
                        ->label('Цена в сумах')
                        ->numeric()
                        ->helperText('Заполните, только если цену зафиксировали — тогда курс не применяется'),

                    Toggle::make('is_active')
                        ->label('Продаётся')
                        ->default(true)
                        ->helperText('Выключенный пакет исчезает из кабинета; уже выставленные счета остаются в силе'),
                ])
                ->columnSpanFull()
                ->columns(3),
        ]);
    }
}
