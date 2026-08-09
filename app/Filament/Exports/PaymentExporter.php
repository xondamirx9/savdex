<?php

namespace App\Filament\Exports;

use App\Models\Payment;
use Filament\Actions\Exports\ExportColumn;
use Filament\Actions\Exports\Exporter;
use Filament\Actions\Exports\Models\Export;
use Illuminate\Support\Str;

class PaymentExporter extends Exporter
{
    protected static ?string $model = Payment::class;

    public static function getColumns(): array
    {
        return [
            ExportColumn::make('id')
                ->label('ID'),
            ExportColumn::make('company.name'),
            ExportColumn::make('payment_method_id'),
            ExportColumn::make('subscription_id'),
            ExportColumn::make('purpose'),
            ExportColumn::make('description'),
            ExportColumn::make('amount'),
            ExportColumn::make('currency'),
            ExportColumn::make('provider'),
            ExportColumn::make('external_id'),
            ExportColumn::make('status'),
            ExportColumn::make('paid_at'),
            ExportColumn::make('invoice_path'),
            ExportColumn::make('created_at'),
            ExportColumn::make('updated_at'),
        ];
    }

    public static function getCompletedNotificationBody(Export $export): string
    {
        $body = 'Your payment export has completed and '.Str::of('row')->counted($export->successful_rows).' exported.';

        if ($failedRowsCount = $export->getFailedRowsCount()) {
            $body .= ' '.Str::of('row')->counted($failedRowsCount).' failed to export.';
        }

        return $body;
    }
}
