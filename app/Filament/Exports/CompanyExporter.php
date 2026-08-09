<?php

declare(strict_types=1);

namespace App\Filament\Exports;

use App\Models\Company;
use Filament\Actions\Exports\ExportColumn;
use Filament\Actions\Exports\Exporter;
use Filament\Actions\Exports\Models\Export;

/**
 * Выгрузка компаний (§6.4 ТЗ).
 *
 * Колонки подписаны по-русски и в том же порядке, что ждёт импорт:
 * выгруженный файл можно поправить в Excel и загрузить обратно,
 * не переставляя столбцы руками.
 */
class CompanyExporter extends Exporter
{
    protected static ?string $model = Company::class;

    public static function getColumns(): array
    {
        return [
            ExportColumn::make('tin')->label('ИНН'),
            ExportColumn::make('name')->label('Название'),
            ExportColumn::make('legal_name')->label('Юридическое название'),
            ExportColumn::make('type')->label('Тип компании'),

            ExportColumn::make('city_id')
                ->label('Город')
                ->state(fn (Company $record): ?string => $record->city?->name()),

            ExportColumn::make('address')->label('Адрес'),
            ExportColumn::make('phone')->label('Телефон'),
            ExportColumn::make('email')->label('Почта'),
            ExportColumn::make('website')->label('Сайт'),
            ExportColumn::make('description')->label('Описание'),
            ExportColumn::make('founded_year')->label('Год основания'),
            ExportColumn::make('employees_range')->label('Сотрудников'),

            ExportColumn::make('verification_level')
                ->label('Верификация')
                ->formatStateUsing(fn ($state): string => match ((int) $state) {
                    3 => 'Проверена+',
                    2 => 'Проверена',
                    1 => 'Контакты подтверждены',
                    default => 'Не проверена',
                }),

            ExportColumn::make('rating')->label('Рейтинг'),
            ExportColumn::make('reviews_count')->label('Отзывов'),
            ExportColumn::make('listings_count')->label('Объявлений')->counts('listings'),

            ExportColumn::make('status')
                ->label('Статус')
                ->formatStateUsing(fn (string $state): string => $state === 'active' ? 'Активна' : 'Заблокирована'),

            ExportColumn::make('created_at')->label('Дата регистрации'),
        ];
    }

    public static function getCompletedNotificationBody(Export $export): string
    {
        $body = 'Выгрузка готова. Строк: '.number_format($export->successful_rows, 0, ',', ' ').'.';

        if (($failed = $export->getFailedRowsCount()) > 0) {
            $body .= ' Не удалось выгрузить: '.number_format($failed, 0, ',', ' ').'.';
        }

        return $body;
    }
}
