<?php

declare(strict_types=1);

namespace App\Filament\Resources\ItTasks\Pages;

use App\Filament\Resources\ItTasks\ItTaskResource;
use Filament\Actions\DeleteAction;
use Filament\Resources\Pages\EditRecord;

class EditItTask extends EditRecord
{
    protected static string $resource = ItTaskResource::class;

    protected function getHeaderActions(): array
    {
        return [DeleteAction::make()];
    }
}
