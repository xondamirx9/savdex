<?php

declare(strict_types=1);

namespace App\Filament\Resources\Tickets;

use App\Filament\Concerns\AuthorizesBySection;
use App\Filament\Resources\Tickets\Pages\CreateTicket;
use App\Filament\Resources\Tickets\Pages\EditTicket;
use App\Filament\Resources\Tickets\Pages\ListTickets;
use App\Filament\Resources\Tickets\Schemas\TicketForm;
use App\Filament\Resources\Tickets\Tables\TicketsTable;
use App\Models\Support\Ticket;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Schemas\Schema;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;
use UnitEnum;

/**
 * Обращения в поддержку.
 *
 * Область видимости не сужается: поддержка работает очередью, и
 * обращение, закреплённое за ушедшим в отпуск сотрудником, не должно
 * пропадать у остальных.
 */
class TicketResource extends Resource
{
    use AuthorizesBySection;

    protected static string $accessSection = 'support';

    protected static ?string $model = Ticket::class;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedLifebuoy;

    protected static ?string $navigationLabel = 'Обращения';

    protected static ?string $modelLabel = 'обращение';

    protected static ?string $pluralModelLabel = 'обращения';

    protected static string|UnitEnum|null $navigationGroup = 'Поддержка';

    protected static ?int $navigationSort = 1;

    /** Счётчик — открытые: обращение без ответа это долг перед клиентом. */
    public static function getNavigationBadge(): ?string
    {
        $count = Ticket::query()->open()->count();

        return $count > 0 ? (string) $count : null;
    }

    public static function getNavigationBadgeColor(): ?string
    {
        return 'warning';
    }

    public static function form(Schema $schema): Schema
    {
        return TicketForm::configure($schema);
    }

    public static function table(Table $table): Table
    {
        return TicketsTable::configure($table);
    }

    public static function getPages(): array
    {
        return [
            'index' => ListTickets::route('/'),
            'create' => CreateTicket::route('/create'),
            'edit' => EditTicket::route('/{record}/edit'),
        ];
    }
}
