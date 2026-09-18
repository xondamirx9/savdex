<?php

declare(strict_types=1);

namespace App\Filament\Resources\Reviews\Pages;

use App\Filament\Resources\Reviews\ReviewResource;
use App\Models\Review;
use Filament\Resources\Pages\CreateRecord;
use Illuminate\Support\Facades\Auth;

class CreateReview extends CreateRecord
{
    protected static string $resource = ReviewResource::class;

    /**
     * Происхождение проставляется кодом, а не формой.
     *
     * Поле, которым можно выдать заведённый отзыв за покупательский,
     * обесценило бы саму пометку.
     *
     * @param  array<string, mixed>  $data
     * @return array<string, mixed>
     */
    protected function mutateFormDataBeforeCreate(array $data): array
    {
        $data['origin'] = Review::ORIGIN_ADMIN;
        $data['created_by'] = Auth::id();

        return $data;
    }
}
