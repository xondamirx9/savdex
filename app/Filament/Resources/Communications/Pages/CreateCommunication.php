<?php

declare(strict_types=1);

namespace App\Filament\Resources\Communications\Pages;

use App\Filament\Resources\Communications\CommunicationResource;
use Filament\Resources\Pages\CreateRecord;

class CreateCommunication extends CreateRecord
{
    protected static string $resource = CommunicationResource::class;

    /** Автор проставляется сам: спрашивать «кто записал» у того, кто записывает, незачем. */
    protected function mutateFormDataBeforeCreate(array $data): array
    {
        $data['author_id'] = auth()->id();

        return $data;
    }
}
