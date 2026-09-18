<?php

declare(strict_types=1);

namespace App\Filament\Resources\Resumes\Pages;

use App\Filament\Resources\Resumes\ResumeResource;
use Filament\Resources\Pages\ListRecords;

class ListResumes extends ListRecords
{
    protected static string $resource = ResumeResource::class;
}
