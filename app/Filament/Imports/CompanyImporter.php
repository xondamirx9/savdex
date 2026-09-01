<?php

declare(strict_types=1);

namespace App\Filament\Imports;

use App\Models\Company;
use App\Support\CompanyNameStyle;
use Filament\Actions\Imports\ImportColumn;
use Filament\Actions\Imports\Importer;
use Filament\Actions\Imports\Models\Import;

/**
 * Импорт компаний из таблицы (§6.4 ТЗ).
 *
 * Сопоставление идёт по ИНН, а не по названию: «ООО Стройбаза»
 * и «ООО «Стройбаза»» — одна компания, а два разных ИНН означают
 * два разных юрлица даже при одинаковом названии.
 *
 * Заголовки колонок русские: файл готовит заказчик в Excel,
 * и требовать от него slug и primary_role бессмысленно.
 */
class CompanyImporter extends Importer
{
    protected static ?string $model = Company::class;

    public static function getColumns(): array
    {
        return [
            ImportColumn::make('tin')
                ->label('ИНН')
                ->exampleHeader('ИНН')
                ->example('304561278')
                ->rules(['nullable', 'string', 'max:20']),

            ImportColumn::make('name')
                ->label('Название')
                ->exampleHeader('Название')
                ->example('ООО «Стройбаза»')
                ->requiredMapping()
                // Госреестр пишет капсом — на витрине это выглядит криком
                ->castStateUsing(fn (?string $state): string => CompanyNameStyle::humanize((string) $state))
                ->rules(['required', 'string', 'max:190']),

            ImportColumn::make('legal_name')
                ->label('Юридическое название')
                ->exampleHeader('Юридическое название')
                ->rules(['nullable', 'string', 'max:255']),

            ImportColumn::make('type')
                ->label('Тип компании')
                ->exampleHeader('Тип компании')
                ->example('distributor')
                // «trading» и «торговая» из таблиц — это trader справочника
                ->castStateUsing(fn (?string $state): ?string => CompanyNameStyle::typeKey($state))
                ->rules(['nullable', 'string', 'max:30']),

            ImportColumn::make('address')
                ->label('Адрес')
                ->exampleHeader('Адрес')
                ->rules(['nullable', 'string', 'max:255']),

            ImportColumn::make('phone')
                ->label('Телефон')
                ->exampleHeader('Телефон')
                ->rules(['nullable', 'string', 'max:40']),

            ImportColumn::make('email')
                ->label('Почта')
                ->exampleHeader('Почта')
                ->rules(['nullable', 'email', 'max:190']),

            ImportColumn::make('website')
                ->label('Сайт')
                ->exampleHeader('Сайт')
                ->rules(['nullable', 'string', 'max:190']),

            ImportColumn::make('description')
                ->label('Описание')
                ->exampleHeader('Описание')
                ->rules(['nullable', 'string', 'max:5000']),

            ImportColumn::make('founded_year')
                ->label('Год основания')
                ->exampleHeader('Год основания')
                ->numeric()
                ->rules(['nullable', 'integer', 'between:1850,'.date('Y')]),

            ImportColumn::make('employees_range')
                ->label('Сотрудников')
                ->exampleHeader('Сотрудников')
                ->example('50-100')
                ->rules(['nullable', 'string', 'max:20']),
        ];
    }

    /**
     * Существующая компания находится по ИНН.
     *
     * Без ИНН создаём новую: сопоставлять по названию опасно —
     * одна опечатка порождает дубль, а слияние двух компаний
     * потом делается только руками.
     */
    public function resolveRecord(): ?Company
    {
        $tin = trim((string) ($this->data['tin'] ?? ''));

        if ($tin === '') {
            return new Company;
        }

        return Company::firstOrNew(['tin' => $tin]);
    }

    /**
     * Импортированные компании не получают верификацию автоматически.
     *
     * Загруженная база — черновик: пока модератор не проверил,
     * карточка не должна выглядеть проверенной.
     */
    protected function beforeSave(): void
    {
        if (! $this->record->exists) {
            $this->record->status = Company::STATUS_ACTIVE;
            $this->record->verification_level = Company::VERIFICATION_NONE;

            // Карточку завела площадка, а не компания — визитка обязана
            // говорить об этом. Текст правится в админке по компании
            $this->record->source_note ??= 'Данные компании взяты из открытых источников. Если это ваша компания — зарегистрируйтесь и напишите в поддержку, чтобы подтвердить профиль и управлять им.';
        }
    }

    public static function getCompletedNotificationBody(Import $import): string
    {
        $body = 'Импорт завершён. Обработано строк: '.number_format($import->successful_rows, 0, ',', ' ').'.';

        if (($failed = $import->getFailedRowsCount()) > 0) {
            // Точное число ошибок и файл с причинами: «часть строк
            // не импортирована» не даёт понять, что именно чинить
            $body .= ' Не удалось импортировать: '.number_format($failed, 0, ',', ' ')
                .'. Скачайте файл с ошибками — в нём причина по каждой строке.';
        }

        return $body;
    }
}
