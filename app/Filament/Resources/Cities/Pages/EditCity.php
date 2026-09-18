<?php

declare(strict_types=1);

namespace App\Filament\Resources\Cities\Pages;

use App\Filament\Resources\Cities\CityResource;
use App\Models\City;
use Filament\Actions\DeleteAction;
use Filament\Resources\Pages\EditRecord;

class EditCity extends EditRecord
{
    protected static string $resource = CityResource::class;

    protected function getHeaderActions(): array
    {
        return [
            DeleteAction::make()
                ->disabled(fn (City $record): bool => $record->isReferenced())
                ->tooltip(fn (City $record): ?string => $record->isReferenced()
                    ? 'Удалить нельзя, на город ссылаются: '.$record->referencesSummary().'. Выключите его вместо удаления.'
                    : null),
        ];
    }
}
