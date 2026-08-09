<?php

declare(strict_types=1);

namespace App\Filament\Resources\LandingBlocks\Pages;

use App\Filament\Resources\LandingBlocks\LandingBlockResource;
use Filament\Actions\CreateAction;
use Filament\Resources\Pages\ListRecords;

class ListLandingBlocks extends ListRecords
{
    protected static string $resource = LandingBlockResource::class;

    /**
     * Заголовок задан явно: Filament поднимает регистр каждого слова
     * и из «блоки главной» получает «Блоки Главной» — по-английски
     * это норма, по-русски выглядит как опечатка.
     */
    public function getTitle(): string
    {
        return 'Блоки главной';
    }

    protected function getHeaderActions(): array
    {
        return [
            CreateAction::make(),
        ];
    }
}
