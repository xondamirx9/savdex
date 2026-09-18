<?php

namespace App\Filament\Resources\Listings\Pages;

use App\Filament\Resources\Listings\ListingResource;
use App\Models\Listing;
use Filament\Actions\DeleteAction;
use Filament\Actions\ForceDeleteAction;
use Filament\Actions\RestoreAction;
use Filament\Resources\Pages\EditRecord;

class EditListing extends EditRecord
{
    protected static string $resource = ListingResource::class;

    protected function getHeaderActions(): array
    {
        return [
            DeleteAction::make(),
            ForceDeleteAction::make(),
            RestoreAction::make(),
        ];
    }

    /**
     * Пустые переводы не хранятся.
     *
     * Форма присылает поле каждого языка, и стёртый перевод приходит
     * пустой строкой. В колонке она означала бы «перевод есть, но
     * пустой» — и витрина показала бы пустой заголовок вместо того,
     * чтобы скрыть объявление на этом языке. Пустой набор становится
     * null: так и загрузка из книги, и машинный переводчик понимают,
     * что переводов нет вовсе.
     *
     * @param  array<string, mixed>  $data
     * @return array<string, mixed>
     */
    protected function mutateFormDataBeforeSave(array $data): array
    {
        foreach (Listing::TRANSLATABLE as $field) {
            $column = $field.'_i18n';

            if (! array_key_exists($column, $data)) {
                continue;
            }

            $kept = array_filter(
                (array) $data[$column],
                fn (mixed $value): bool => trim((string) $value) !== '',
            );

            $data[$column] = $kept === [] ? null : array_map(trim(...), $kept);
        }

        return $data;
    }
}
