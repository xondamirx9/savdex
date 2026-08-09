<?php

declare(strict_types=1);

namespace App\Filament\Exports;

use App\Models\Listing;
use Filament\Actions\Exports\ExportColumn;
use Filament\Actions\Exports\Exporter;
use Filament\Actions\Exports\Models\Export;

/** Выгрузка объявлений со статистикой (§6.4 ТЗ). */
class ListingExporter extends Exporter
{
    protected static ?string $model = Listing::class;

    public static function getColumns(): array
    {
        return [
            ExportColumn::make('id')->label('Номер'),
            ExportColumn::make('title')->label('Заголовок'),
            ExportColumn::make('company.name')->label('Компания'),

            ExportColumn::make('category_id')
                ->label('Категория')
                ->state(fn (Listing $record): ?string => $record->category?->name()),

            ExportColumn::make('type')
                ->label('Тип')
                ->formatStateUsing(fn (string $state): string => $state === 'demand' ? 'Запрос' : 'Предложение'),

            ExportColumn::make('price')->label('Цена'),
            ExportColumn::make('currency')->label('Валюта'),
            ExportColumn::make('unit')->label('Единица'),

            ExportColumn::make('status')
                ->label('Статус')
                ->formatStateUsing(fn (string $state): string => match ($state) {
                    Listing::STATUS_ACTIVE => 'Активно',
                    Listing::STATUS_MODERATION => 'На проверке',
                    Listing::STATUS_DRAFT => 'Черновик',
                    Listing::STATUS_REJECTED => 'Отклонено',
                    Listing::STATUS_EXPIRED => 'Истекло',
                    default => 'Снято',
                }),

            ExportColumn::make('impressions_count')->label('Показы'),
            ExportColumn::make('views_count')->label('Просмотры'),
            ExportColumn::make('unlocks_count')->label('Раскрытий контакта'),
            ExportColumn::make('published_at')->label('Опубликовано'),
            ExportColumn::make('expires_at')->label('Действует до'),
        ];
    }

    public static function getCompletedNotificationBody(Export $export): string
    {
        return 'Выгрузка готова. Строк: '.number_format($export->successful_rows, 0, ',', ' ').'.';
    }
}
