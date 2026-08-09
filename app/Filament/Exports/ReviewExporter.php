<?php

namespace App\Filament\Exports;

use App\Models\Review;
use Filament\Actions\Exports\ExportColumn;
use Filament\Actions\Exports\Exporter;
use Filament\Actions\Exports\Models\Export;
use Illuminate\Support\Str;

class ReviewExporter extends Exporter
{
    protected static ?string $model = Review::class;

    public static function getColumns(): array
    {
        return [
            ExportColumn::make('id')
                ->label('ID'),
            ExportColumn::make('company.name'),
            ExportColumn::make('authorCompany.name'),
            ExportColumn::make('author_user_id'),
            ExportColumn::make('contact_unlock_id'),
            ExportColumn::make('listing.title'),
            ExportColumn::make('rating'),
            ExportColumn::make('rating_description'),
            ExportColumn::make('rating_response'),
            ExportColumn::make('rating_deadlines'),
            ExportColumn::make('rating_quality'),
            ExportColumn::make('body'),
            ExportColumn::make('deal_confirmed'),
            ExportColumn::make('reply'),
            ExportColumn::make('replied_at'),
            ExportColumn::make('dispute_status'),
            ExportColumn::make('dispute_reason'),
            ExportColumn::make('status'),
            ExportColumn::make('created_at'),
            ExportColumn::make('updated_at'),
        ];
    }

    public static function getCompletedNotificationBody(Export $export): string
    {
        $body = 'Your review export has completed and '.Str::of('row')->counted($export->successful_rows).' exported.';

        if ($failedRowsCount = $export->getFailedRowsCount()) {
            $body .= ' '.Str::of('row')->counted($failedRowsCount).' failed to export.';
        }

        return $body;
    }
}
