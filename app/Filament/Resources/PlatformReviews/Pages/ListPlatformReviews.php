<?php

declare(strict_types=1);

namespace App\Filament\Resources\PlatformReviews\Pages;

use App\Filament\Resources\PlatformReviews\PlatformReviewResource;
use Filament\Resources\Pages\ListRecords;

class ListPlatformReviews extends ListRecords
{
    protected static string $resource = PlatformReviewResource::class;
}
