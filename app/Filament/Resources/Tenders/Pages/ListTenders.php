<?php

declare(strict_types=1);

namespace App\Filament\Resources\Tenders\Pages;

use App\Filament\Resources\Tenders\TenderResource;
use Filament\Resources\Pages\ListRecords;

class ListTenders extends ListRecords
{
    protected static string $resource = TenderResource::class;
}
