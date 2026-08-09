<?php

namespace App\Filament\Resources\LandingBlocks\Pages;

use App\Filament\Resources\LandingBlocks\LandingBlockResource;
use Filament\Actions\DeleteAction;
use Filament\Resources\Pages\EditRecord;

class EditLandingBlock extends EditRecord
{
    protected static string $resource = LandingBlockResource::class;

    protected function getHeaderActions(): array
    {
        return [
            DeleteAction::make(),
        ];
    }
}
