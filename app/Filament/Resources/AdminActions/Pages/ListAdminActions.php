<?php

declare(strict_types=1);

namespace App\Filament\Resources\AdminActions\Pages;

use App\Filament\Resources\AdminActions\AdminActionResource;
use Filament\Resources\Pages\ListRecords;

class ListAdminActions extends ListRecords
{
    protected static string $resource = AdminActionResource::class;

    /** Записи журнала не заводят руками — их оставляют действия. */
    protected function getHeaderActions(): array
    {
        return [];
    }
}
