<?php

declare(strict_types=1);

namespace App\Filament\Resources\Subscriptions\Pages;

use App\Filament\Resources\Subscriptions\SubscriptionResource;
use Filament\Resources\Pages\ListRecords;

class ListSubscriptions extends ListRecords
{
    protected static string $resource = SubscriptionResource::class;

    /**
     * Кнопки «Создать» здесь нет: выдача тарифа живёт в шапке таблицы
     * и проходит через SubscriptionService — см. комментарий ресурса.
     */
    protected function getHeaderActions(): array
    {
        return [];
    }
}
