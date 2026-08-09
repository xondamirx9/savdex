<?php

declare(strict_types=1);

namespace App\Filament\Resources\Listings\Pages;

use App\Filament\Resources\Listings\ListingResource;
use Filament\Resources\Pages\ListRecords;

class ListListings extends ListRecords
{
    protected static string $resource = ListingResource::class;

    /**
     * Кнопки «Создать» нет: объявление публикует компания от своего
     * имени — у него есть владелец, автор и слот в тарифе. Заведённое
     * из админки объявление не принадлежало бы никому.
     */
    protected function getHeaderActions(): array
    {
        return [];
    }
}
