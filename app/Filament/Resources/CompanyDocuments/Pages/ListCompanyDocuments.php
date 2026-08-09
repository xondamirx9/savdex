<?php

declare(strict_types=1);

namespace App\Filament\Resources\CompanyDocuments\Pages;

use App\Filament\Resources\CompanyDocuments\CompanyDocumentResource;
use Filament\Resources\Pages\ListRecords;

class ListCompanyDocuments extends ListRecords
{
    protected static string $resource = CompanyDocumentResource::class;

    /** Документ загружает компания — из админки его не создают. */
    protected function getHeaderActions(): array
    {
        return [];
    }
}
