<?php

namespace App\Filament\Exports;

use App\Models\ContactUnlock;
use Filament\Actions\Exports\ExportColumn;
use Filament\Actions\Exports\Exporter;
use Filament\Actions\Exports\Models\Export;
use Illuminate\Support\Str;

class ContactUnlockExporter extends Exporter
{
    protected static ?string $model = ContactUnlock::class;

    public static function getColumns(): array
    {
        return [
            ExportColumn::make('id')
                ->label('ID'),
            ExportColumn::make('company.name'),
            ExportColumn::make('targetCompany.name'),
            ExportColumn::make('user_id'),
            ExportColumn::make('listing.title'),
            ExportColumn::make('credits_spent'),
            ExportColumn::make('status'),
            ExportColumn::make('note'),
            ExportColumn::make('complaint_status'),
            ExportColumn::make('complaint_reason'),
            ExportColumn::make('complained_at'),
            ExportColumn::make('refunded'),
            ExportColumn::make('created_at'),
            ExportColumn::make('updated_at'),
        ];
    }

    public static function getCompletedNotificationBody(Export $export): string
    {
        $body = 'Your contact unlock export has completed and '.Str::of('row')->counted($export->successful_rows).' exported.';

        if ($failedRowsCount = $export->getFailedRowsCount()) {
            $body .= ' '.Str::of('row')->counted($failedRowsCount).' failed to export.';
        }

        return $body;
    }
}
