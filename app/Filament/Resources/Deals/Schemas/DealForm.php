<?php

declare(strict_types=1);

namespace App\Filament\Resources\Deals\Schemas;

use App\Models\Crm\Contact;
use App\Models\Crm\Deal;
use App\Models\User;
use Filament\Forms\Components\DatePicker;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\Textarea;
use Filament\Forms\Components\TextInput;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Components\Utilities\Get;
use Filament\Schemas\Schema;
use Illuminate\Support\Facades\Auth;

class DealForm
{
    public static function configure(Schema $schema): Schema
    {
        return $schema->components([
            Section::make('Сделка')
                ->schema([
                    TextInput::make('title')
                        ->label('Название')
                        ->required()
                        ->maxLength(200)
                        ->columnSpanFull(),

                    Select::make('stage')
                        ->label('Этап')
                        ->options(Deal::STAGES)
                        ->default(Deal::STAGE_NEW)
                        ->required()
                        ->live(),

                    Select::make('owner_id')
                        ->label('Ответственный')
                        ->options(fn (): array => self::employees())
                        ->default(fn (): ?int => Auth::id())
                        ->searchable()
                        ->required(),

                    DatePicker::make('expected_close_at')
                        ->label('Ждём закрытия')
                        ->displayFormat('d.m.Y')
                        ->helperText('Без даты сделка выпадает из планирования'),
                ])
                ->columns(3),

            Section::make('Сумма')
                ->schema([
                    TextInput::make('amount')
                        ->label('Сумма')
                        ->numeric()
                        ->minValue(0)
                        ->default(0)
                        // Целым числом: сумы без копеек, а дробное
                        // хранение денег однажды покажет 1 999 999.99
                        ->step(1)
                        ->helperText('Целым числом, без копеек'),

                    Select::make('currency')
                        ->label('Валюта')
                        ->options(Deal::CURRENCIES)
                        ->default('UZS')
                        ->required(),
                ])
                ->columns(2),

            Section::make('Клиент')
                ->schema([
                    Select::make('company_id')
                        ->label('Компания')
                        ->relationship('company', 'name')
                        ->searchable()
                        ->preload(),

                    Select::make('contact_id')
                        ->label('Контакт')
                        ->options(fn (Get $get): array => self::contacts($get('company_id')))
                        ->searchable(),
                ])
                ->columns(2),

            Section::make('Работа по сделке')
                ->schema([
                    Textarea::make('note')
                        ->label('Заметки')
                        ->rows(4)
                        ->columnSpanFull(),

                    Textarea::make('lost_reason')
                        ->label('Причина проигрыша')
                        ->rows(2)
                        ->columnSpanFull()
                        // Проигранная сделка без причины ничему не учит,
                        // а разбирают в первую очередь именно проигрыши
                        ->required(fn (Get $get): bool => $get('stage') === Deal::STAGE_LOST)
                        ->visible(fn (Get $get): bool => $get('stage') === Deal::STAGE_LOST)
                        ->helperText('Обязательно: цена, сроки, конкурент, передумали'),
                ]),
        ]);
    }

    /** @return array<int, string> */
    private static function employees(): array
    {
        return User::query()
            ->where('is_admin', true)
            ->where('status', 'active')
            ->orderBy('name')
            ->get(['id', 'name', 'admin_role', 'is_admin', 'admin_permissions'])
            ->filter(fn (User $u): bool => $u->hasAdminAbility('deals.view'))
            ->pluck('name', 'id')
            ->all();
    }

    /** @return array<int, string> */
    private static function contacts(mixed $companyId): array
    {
        return Contact::query()
            ->when($companyId !== null, fn ($q) => $q->where('company_id', $companyId))
            ->orderBy('name')
            ->limit(100)
            ->get()
            ->mapWithKeys(fn (Contact $c): array => [$c->id => $c->label()])
            ->all();
    }
}
