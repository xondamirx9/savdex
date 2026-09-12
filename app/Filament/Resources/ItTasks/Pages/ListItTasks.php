<?php

declare(strict_types=1);

namespace App\Filament\Resources\ItTasks\Pages;

use App\Filament\Resources\ItTasks\ItTaskResource;
use Filament\Resources\Pages\ListRecords;

class ListItTasks extends ListRecords
{
    protected static string $resource = ItTaskResource::class;
}
