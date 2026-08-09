<?php

namespace App\Filament\Resources\CompanyTypes\Pages;

use App\Filament\Resources\CompanyTypes\CompanyTypeResource;
use Filament\Resources\Pages\CreateRecord;

class CreateCompanyType extends CreateRecord
{
    protected static string $resource = CompanyTypeResource::class;
}
