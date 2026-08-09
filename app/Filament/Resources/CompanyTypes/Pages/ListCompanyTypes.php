<?php

declare(strict_types=1);

namespace App\Filament\Resources\CompanyTypes\Pages;

use App\Filament\Resources\CompanyTypes\CompanyTypeResource;
use Filament\Actions\CreateAction;
use Filament\Resources\Pages\ListRecords;

class ListCompanyTypes extends ListRecords
{
    protected static string $resource = CompanyTypeResource::class;

    /**
     * Заголовок задан явно: Filament поднимает регистр каждого слова
     * и из «типы компаний» получает «Типы Компаний» — по-английски
     * это норма, по-русски выглядит как опечатка.
     */
    public function getTitle(): string
    {
        return 'Типы компаний';
    }

    protected function getHeaderActions(): array
    {
        return [
            CreateAction::make(),
        ];
    }
}
