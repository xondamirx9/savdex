<?php

declare(strict_types=1);

namespace App\Filament\Resources\Communications\Pages;

use App\Filament\Resources\Communications\CommunicationResource;
use Filament\Actions\CreateAction;
use Filament\Resources\Pages\ListRecords;

class ListCommunications extends ListRecords
{
    protected static string $resource = CommunicationResource::class;

    protected function getHeaderActions(): array
    {
        return [CreateAction::make()->label('Записать разговор')];
    }
}
