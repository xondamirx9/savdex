<?php

declare(strict_types=1);

namespace App\Filament\Resources\Companies\Schemas;

use App\Models\City;
use App\Models\Company;
use App\Models\Country;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\Textarea;
use Filament\Forms\Components\TextInput;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Schema;

/**
 * Карточка компании в админке.
 *
 * Форма правит то, что компания заполняет о себе сама: поддержка
 * исправляет ИНН с опечаткой, дописывает адрес по телефону, чистит
 * описание после жалобы.
 *
 * Уровень верификации и блокировка сюда не вынесены намеренно.
 * Это не поля, а решения: они уходят уведомлением владельцу и
 * записываются в журнал, поэтому у них отдельные действия в списке.
 * Выпадающий список «уровень проверки» рядом с адресом превращает
 * выдачу бейджа в правку реквизита.
 */
class CompanyForm
{
    private const EMPLOYEE_RANGES = ['1-10', '10-50', '50-100', '100-500', '500+'];

    private const ROLES = [
        'supplier' => 'Поставщик',
        'buyer' => 'Закупщик',
        'both' => 'И то, и другое',
    ];

    public static function configure(Schema $schema): Schema
    {
        return $schema->components([
            Section::make('Компания')
                ->schema([
                    TextInput::make('name')
                        ->label('Название')
                        ->required()
                        ->maxLength(190)
                        ->columnSpan(2),

                    TextInput::make('legal_name')
                        ->label('Юридическое название')
                        ->maxLength(190)
                        ->placeholder('ООО «Стройбаза»')
                        ->columnSpan(2),

                    TextInput::make('tin')
                        ->label('ИНН')
                        ->maxLength(20)
                        // Уникальность не ставим: ИНН заполняют не все,
                        // а нулевые значения в проверке не участвуют
                        ->helperText('9 цифр для Узбекистана'),

                    Select::make('type')
                        ->label('Тип')
                        ->options(fn (): array => Company::typeOptions())
                        ->searchable()
                        ->helperText('Список правится в справочнике «Типы компаний»'),

                    Select::make('primary_role')
                        ->label('Роль на площадке')
                        ->options(self::ROLES)
                        ->required()
                        ->default('both'),

                    TextInput::make('founded_year')
                        ->label('Год основания')
                        ->numeric()
                        ->minValue(1800)
                        ->maxValue((int) date('Y')),
                ])
                ->columnSpanFull()
                ->columns(4),

            Section::make('Где находится')
                ->schema([
                    Select::make('country_id')
                        ->label('Страна')
                        ->options(fn (): array => Country::query()
                            ->with('translations')
                            ->orderBy('sort')
                            ->get()
                            ->mapWithKeys(fn (Country $c): array => [$c->id => $c->name()])
                            ->all())
                        ->searchable()
                        // Город из другой страны — рассинхрон, который
                        // потом ищут в данных руками
                        ->live()
                        ->afterStateUpdated(fn ($set) => $set('city_id', null)),

                    Select::make('city_id')
                        ->label('Город')
                        ->options(fn ($get): array => City::query()
                            ->where('country_id', $get('country_id'))
                            ->with('translations')
                            ->get()
                            ->mapWithKeys(fn (City $c): array => [$c->id => $c->name()])
                            ->all())
                        ->searchable()
                        ->placeholder(fn ($get): string => $get('country_id') ? 'Выберите город' : 'Сначала выберите страну'),

                    TextInput::make('address')
                        ->label('Адрес')
                        ->maxLength(255)
                        ->columnSpan(2),
                ])
                ->columnSpanFull()
                ->columns(4),

            Section::make('Контакты')
                ->description('Основные контакты карточки. Развёрнутый список компания ведёт у себя в кабинете.')
                ->schema([
                    TextInput::make('phone')->label('Телефон')->tel()->maxLength(32),
                    TextInput::make('email')->label('Почта')->email()->maxLength(190),
                    TextInput::make('website')->label('Сайт')->url()->maxLength(190),
                    TextInput::make('contact_person')->label('Контактное лицо')->maxLength(120),
                    TextInput::make('telegram')->label('Telegram')->maxLength(64)->prefix('@'),
                    TextInput::make('whatsapp')->label('WhatsApp')->tel()->maxLength(32),
                ])
                ->columnSpanFull()
                ->columns(3),

            Section::make('О компании')
                ->schema([
                    Textarea::make('description')
                        ->label('Описание')
                        ->rows(5)
                        ->maxLength(5000)
                        ->helperText('Видно на визитке. Профиль с описанием получает заметно больше обращений'),

                    Select::make('employees_range')
                        ->label('Сотрудников')
                        ->options(array_combine(self::EMPLOYEE_RANGES, self::EMPLOYEE_RANGES))
                        ->placeholder('не указано'),

                    TextInput::make('response_time_hours')
                        ->label('Отвечает за, часов')
                        ->numeric()
                        ->minValue(0)
                        ->helperText('Показывается на визитке как ожидание ответа'),
                ])
                ->columnSpanFull()
                ->columns(2),
        ]);
    }
}
