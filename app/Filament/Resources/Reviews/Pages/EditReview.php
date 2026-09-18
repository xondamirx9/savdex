<?php

declare(strict_types=1);

namespace App\Filament\Resources\Reviews\Pages;

use App\Filament\Resources\Reviews\ReviewResource;
use Filament\Actions\DeleteAction;
use Filament\Resources\Pages\EditRecord;

class EditReview extends EditRecord
{
    protected static string $resource = ReviewResource::class;

    protected function getHeaderActions(): array
    {
        return [
            /*
             * Удаление отзыва — не то же, что скрытие. Скрытый остаётся
             * в базе и в истории спора; удалять стоит только то, чего
             * не должно было быть вовсе: спам, клевету, чужие
             * персональные данные.
             *
             * Право на удаление — суперадминское (см. AuthorizesBySection).
             */
            DeleteAction::make(),
        ];
    }
}
