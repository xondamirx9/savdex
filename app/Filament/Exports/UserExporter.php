<?php

declare(strict_types=1);

namespace App\Filament\Exports;

use App\Models\User;
use Filament\Actions\Exports\ExportColumn;
use Filament\Actions\Exports\Exporter;
use Filament\Actions\Exports\Models\Export;

/**
 * Выгрузка пользователей (§6.4 ТЗ).
 *
 * Пароля и токенов в списке колонок нет вовсе: файл уходит на чужой
 * компьютер и живёт там неизвестно сколько. Хеш пароля в такой
 * выгрузке — это утечка, пусть и отложенная.
 */
class UserExporter extends Exporter
{
    protected static ?string $model = User::class;

    public static function getColumns(): array
    {
        return [
            ExportColumn::make('name')->label('Имя'),
            ExportColumn::make('email')->label('Почта'),
            ExportColumn::make('phone')->label('Телефон'),
            ExportColumn::make('company.name')->label('Компания'),

            ExportColumn::make('company_role')
                ->label('Роль в компании')
                ->formatStateUsing(fn (?string $state): string => $state === 'owner' ? 'Владелец' : 'Сотрудник'),

            ExportColumn::make('admin_role')
                ->label('Роль в админке')
                ->state(fn (User $record): ?string => $record->adminRoleLabel()),

            ExportColumn::make('email_verified_at')->label('Почта подтверждена'),

            ExportColumn::make('status')
                ->label('Статус')
                ->formatStateUsing(fn (string $state): string => $state === 'active' ? 'Активен' : 'Заблокирован'),

            ExportColumn::make('last_login_at')->label('Последний вход'),
            ExportColumn::make('created_at')->label('Регистрация'),
        ];
    }

    public static function getCompletedNotificationBody(Export $export): string
    {
        return 'Выгрузка готова. Строк: '.number_format($export->successful_rows, 0, ',', ' ').'.';
    }
}
