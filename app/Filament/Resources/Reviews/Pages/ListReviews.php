<?php

declare(strict_types=1);

namespace App\Filament\Resources\Reviews\Pages;

use App\Filament\Imports\ReviewImporter;
use App\Filament\Resources\Reviews\ReviewResource;
use App\Support\AdminAccess;
use Filament\Actions\CreateAction;
use Filament\Actions\ImportAction;
use Filament\Resources\Pages\ListRecords;

class ListReviews extends ListRecords
{
    protected static string $resource = ReviewResource::class;

    /**
     * Обычный путь отзыва — от покупателя из кабинета. Но собранные
     * вне сайта тоже нужно уметь внести: перенос со старой площадки,
     * отзывы с выставки, присланные почтой.
     *
     * Всё заведённое отсюда помечается происхождением, и в таблице
     * видно, какая часть рейтинга пришла от покупателей, а какая
     * заведена вручную.
     */
    protected function getHeaderActions(): array
    {
        return [
            CreateAction::make()->label('Завести отзыв'),

            ImportAction::make()
                ->importer(ReviewImporter::class)
                ->label('Загрузить файлом')
                ->color('gray')
                // Загрузка создаёт записи пачкой мимо формы и её
                // проверок, поэтому право на неё отдельное
                ->visible(fn (): bool => AdminAccess::allows('reviews.import')),
        ];
    }
}
