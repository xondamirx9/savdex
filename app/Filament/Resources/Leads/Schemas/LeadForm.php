<?php

declare(strict_types=1);

namespace App\Filament\Resources\Leads\Schemas;

use App\Models\Crm\Contact;
use App\Models\Crm\Lead;
use App\Models\User;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\Textarea;
use Filament\Forms\Components\TextInput;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Components\Utilities\Get;
use Filament\Schemas\Schema;
use Illuminate\Support\Facades\Auth;

class LeadForm
{
    public static function configure(Schema $schema): Schema
    {
        return $schema->components([
            Section::make('Заявка')
                ->schema([
                    TextInput::make('title')
                        ->label('Суть обращения')
                        ->required()
                        ->maxLength(200)
                        ->columnSpanFull()
                        ->helperText('Коротко, своими словами: «Ищет поставщика цемента на постоянку»'),

                    Select::make('source')
                        ->label('Откуда пришёл')
                        ->options(Lead::SOURCES)
                        ->default('site')
                        ->required(),

                    Select::make('status')
                        ->label('Статус')
                        ->options(Lead::STATUSES)
                        ->default(Lead::STATUS_NEW)
                        ->required()
                        ->live(),

                    Select::make('owner_id')
                        ->label('Ответственный')
                        ->options(fn (): array => self::employees())
                        ->searchable()
                        // Пусто — значит «общий»: такой лид виден всем
                        // продавцам, пока кто-то не возьмёт его себе
                        ->default(fn (): ?int => Auth::id())
                        ->placeholder('Не распределён — виден всем продавцам'),
                ])
                ->columns(3),

            Section::make('Кто обратился')
                ->description('Карточку контакта можно завести позже — заявка приходит раньше, чем становится понятно, что это не случайность')
                ->schema([
                    Select::make('company_id')
                        ->label('Компания на площадке')
                        ->relationship('company', 'name')
                        ->searchable()
                        ->preload()
                        ->placeholder('Не найдена или ещё не зарегистрирована'),

                    Select::make('contact_id')
                        ->label('Контакт')
                        ->options(fn (Get $get): array => self::contacts($get('company_id')))
                        ->searchable()
                        ->placeholder('Ещё не заведён'),

                    TextInput::make('contact_name')
                        ->label('Имя из заявки')
                        ->maxLength(160),

                    TextInput::make('contact_phone')
                        ->label('Телефон')
                        ->tel()
                        ->maxLength(40),

                    TextInput::make('contact_email')
                        ->label('Почта')
                        ->email()
                        ->maxLength(160),
                ])
                ->columns(3),

            Section::make('Работа по лиду')
                ->schema([
                    Textarea::make('note')
                        ->label('Заметки')
                        ->rows(4)
                        ->columnSpanFull(),

                    Textarea::make('lost_reason')
                        ->label('Причина отказа')
                        ->rows(2)
                        ->columnSpanFull()
                        // Отказ без причины ничему не учит: через месяц
                        // никто не вспомнит, почему клиент не пошёл
                        ->required(fn (Get $get): bool => $get('status') === Lead::STATUS_LOST)
                        ->visible(fn (Get $get): bool => $get('status') === Lead::STATUS_LOST)
                        ->helperText('Обязательно: отказы разбирают, чтобы не повторять'),
                ]),
        ]);
    }

    /**
     * Кого можно назначить ответственным.
     *
     * Только те, кому раздел лидов вообще доступен: назначить лид
     * контент-менеджеру можно один раз, а искать, куда он делся, — долго.
     *
     * @return array<int, string>
     */
    private static function employees(): array
    {
        return User::query()
            ->where('is_admin', true)
            ->where('status', 'active')
            ->orderBy('name')
            ->get(['id', 'name', 'admin_role', 'is_admin', 'admin_permissions'])
            ->filter(fn (User $u): bool => $u->hasAdminAbility('leads.view'))
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
