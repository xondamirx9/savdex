<?php

declare(strict_types=1);

namespace App\Filament\Resources\Tickets\Pages;

use App\Filament\Resources\Tickets\TicketResource;
use Filament\Actions\CreateAction;
use Filament\Resources\Pages\ListRecords;

class ListTickets extends ListRecords
{
    protected static string $resource = TicketResource::class;

    protected function getHeaderActions(): array
    {
        // Обращение заводят руками, когда клиент позвонил или написал
        // на личную почту: иначе такие разговоры нигде не остаются
        return [CreateAction::make()->label('Завести обращение')];
    }
}
