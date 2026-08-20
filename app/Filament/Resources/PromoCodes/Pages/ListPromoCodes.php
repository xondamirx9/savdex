<?php

declare(strict_types=1);

namespace App\Filament\Resources\PromoCodes\Pages;

use App\Filament\Resources\PromoCodes\PromoCodeResource;
use Filament\Resources\Pages\ListRecords;

/**
 * Список промокодов.
 *
 * Кнопки «Создать» нет: коды выпускаются пачкой действием «Выпустить
 * коды» в шапке таблицы — код, придуманный руками, предсказуем.
 */
class ListPromoCodes extends ListRecords
{
    protected static string $resource = PromoCodeResource::class;
}
