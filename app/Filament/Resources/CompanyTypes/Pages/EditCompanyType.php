<?php

namespace App\Filament\Resources\CompanyTypes\Pages;

use App\Filament\Resources\CompanyTypes\CompanyTypeResource;
use Filament\Actions\DeleteAction;
use Filament\Resources\Pages\EditRecord;

class EditCompanyType extends EditRecord
{
    protected static string $resource = CompanyTypeResource::class;

    protected function getHeaderActions(): array
    {
        return [
            DeleteAction::make(),
        ];
    }
}
