<?php

declare(strict_types=1);

namespace App\Filament\Resources\Tenders\Pages;

use App\Filament\Resources\Tenders\TenderResource;
use Filament\Resources\Pages\CreateRecord;
use Illuminate\Support\Facades\Auth;

class CreateTender extends CreateRecord
{
    protected static string $resource = TenderResource::class;

    /** @param array<string, mixed> $data */
    protected function mutateFormDataBeforeCreate(array $data): array
    {
        $data['author_id'] = Auth::id();

        return $data;
    }
}
