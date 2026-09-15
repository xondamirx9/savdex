<?php

declare(strict_types=1);

namespace App\Filament\Resources\Refunds\Pages;

use App\Filament\Resources\Refunds\RefundResource;
use Filament\Resources\Pages\ListRecords;

class ListRefunds extends ListRecords
{
    protected static string $resource = RefundResource::class;

    /** Возврат заводится кнопкой в таблице: ему нужен счёт, а не пустая форма. */
    protected function getHeaderActions(): array
    {
        return [];
    }
}
