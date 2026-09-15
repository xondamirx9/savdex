<?php

declare(strict_types=1);

namespace App\Filament\Resources\Tickets\Schemas;

use App\Models\Support\Ticket;
use App\Models\User;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\TextInput;
use Filament\Schemas\Components\Section;
use Filament\Schemas\Schema;

class TicketForm
{
    public static function configure(Schema $schema): Schema
    {
        return $schema->components([
            Section::make('Обращение')
                ->schema([
                    TextInput::make('subject')
                        ->label('Тема')
                        ->required()
                        ->maxLength(200)
                        ->columnSpanFull(),

                    Select::make('status')
                        ->label('Статус')
                        ->options(Ticket::STATUSES)
                        ->default(Ticket::STATUS_OPEN)
                        ->required(),

                    Select::make('priority')
                        ->label('Важность')
                        ->options(Ticket::PRIORITIES)
                        ->default('normal')
                        ->required(),

                    Select::make('channel')
                        ->label('Откуда пришло')
                        ->options(Ticket::CHANNELS)
                        ->default('form')
                        ->required(),

                    Select::make('assignee_id')
                        ->label('Кто ведёт')
                        ->options(fn (): array => self::staff())
                        ->searchable()
                        ->placeholder('Не назначен — виден всей поддержке'),
                ])
                ->columns(4),

            Section::make('Кто обратился')
                ->description('Обращение бывает и от того, кто не смог войти, — тогда заполняются имя и почта')
                ->schema([
                    Select::make('user_id')
                        ->label('Пользователь')
                        ->relationship('user', 'email')
                        ->searchable()
                        ->preload(),

                    Select::make('company_id')
                        ->label('Компания')
                        ->relationship('company', 'name')
                        ->searchable()
                        ->preload(),

                    TextInput::make('author_name')
                        ->label('Имя из обращения')
                        ->maxLength(160),

                    TextInput::make('author_email')
                        ->label('Почта из обращения')
                        ->email()
                        ->maxLength(160),
                ])
                ->columns(2),
        ]);
    }

    /** @return array<int, string> */
    private static function staff(): array
    {
        return User::query()
            ->where('is_admin', true)
            ->where('status', 'active')
            ->orderBy('name')
            ->get(['id', 'name', 'admin_role', 'is_admin', 'admin_permissions'])
            ->filter(fn (User $u): bool => $u->hasAdminAbility('support.view'))
            ->pluck('name', 'id')
            ->all();
    }
}
