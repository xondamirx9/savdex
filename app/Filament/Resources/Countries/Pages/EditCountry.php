<?php

declare(strict_types=1);

namespace App\Filament\Resources\Countries\Pages;

use App\Filament\Resources\Countries\CountryResource;
use App\Models\Country;
use Filament\Actions\DeleteAction;
use Filament\Resources\Pages\EditRecord;

class EditCountry extends EditRecord
{
    protected static string $resource = CountryResource::class;

    protected function getHeaderActions(): array
    {
        return [
            // Тот же запрет, что и в списке: страна с городами или
            // компаниями не удаляется, её выключают
            DeleteAction::make()
                ->disabled(fn (Country $record): bool => $record->isReferenced())
                ->tooltip(fn (Country $record): ?string => $record->isReferenced()
                    ? 'Удалить нельзя, на страну ссылаются: '.$record->referencesSummary().'. Выключите её вместо удаления.'
                    : null),
        ];
    }
}
