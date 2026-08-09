<?php

namespace App\Filament\Resources\NewsPosts\Pages;

use App\Filament\Resources\NewsPosts\NewsPostResource;
use Filament\Resources\Pages\CreateRecord;

class CreateNewsPost extends CreateRecord
{
    protected static string $resource = NewsPostResource::class;
}
