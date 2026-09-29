<?php

declare(strict_types=1);

namespace App\Filament\Resources\Users;

use App\Models\User;
use Filament\Actions\DeleteAction;
use Filament\Actions\DeleteBulkAction;
use Filament\Actions\ForceDeleteAction;
use Filament\Actions\ForceDeleteBulkAction;
use Filament\Actions\RestoreAction;
use Filament\Actions\RestoreBulkAction;
use Illuminate\Support\Facades\Auth;

/**
 * Удаление аккаунта в два шага — одни и те же кнопки в списке и на
 * странице пользователя.
 *
 * 1. «Отключить» (SoftDeletes): войти нельзя, адрес почты сразу свободен
 *    для новой регистрации, запись остаётся в базе.
 * 2. Отключённый находится фильтром «Отключённые» — и либо
 *    восстанавливается, либо удаляется навсегда (только суперадмин).
 *
 * Права — явно на каждой кнопке. Filament проверяет стандартные действия
 * по политикам модели, а политики у пользователей нет: без visible()
 * «Удалить навсегда» видел любой, кому открыта правка пользователей.
 */
final class UserDeletionActions
{
    public static function disable(): DeleteAction
    {
        return DeleteAction::make()
            ->label('Отключить')
            ->modalHeading(fn (User $record): string => "Отключить аккаунт {$record->email}?")
            ->modalDescription('Войти в аккаунт будет нельзя, а адрес почты сразу освободится для новой регистрации. Запись останется в базе: её можно найти фильтром «Отключённые» и восстановить или удалить навсегда.')
            ->modalSubmitActionLabel('Отключить')
            ->successNotificationTitle('Аккаунт отключён')
            // Отключить себя — остаться без доступа к панели, из которой
            // это можно исправить
            ->visible(fn (User $record): bool => UserResource::canDelete($record) && ! self::isSelf($record));
    }

    public static function restore(): RestoreAction
    {
        return RestoreAction::make()
            ->modalHeading(fn (User $record): string => "Восстановить аккаунт {$record->email}?")
            ->successNotificationTitle('Аккаунт восстановлен')
            // Модель не даёт восстановить, если адрес занял новый аккаунт
            ->failureNotificationTitle(fn (User $record): string => "Не восстановлен: адрес {$record->email} уже занят другим аккаунтом")
            ->hidden(fn (User $record): bool => ! UserResource::canRestore($record));
    }

    public static function forceDelete(): ForceDeleteAction
    {
        return ForceDeleteAction::make()
            ->modalHeading(fn (User $record): string => "Удалить аккаунт {$record->email} навсегда?")
            ->modalDescription('Аккаунт и его личные данные — избранное, уведомления, резюме — будут стёрты из базы. Компания, объявления и платежи останутся, но без ссылки на этого человека. Отменить нельзя.')
            ->successNotificationTitle('Аккаунт удалён навсегда')
            ->hidden(fn (User $record): bool => ! UserResource::canForceDelete($record) || self::isSelf($record));
    }

    public static function disableBulk(): DeleteBulkAction
    {
        return DeleteBulkAction::make()
            ->label('Отключить выбранные')
            ->modalDescription('Войти в эти аккаунты будет нельзя, адреса почты освободятся. Записи останутся в базе.')
            ->visible(fn (): bool => UserResource::canDeleteAny());
    }

    public static function restoreBulk(): RestoreBulkAction
    {
        return RestoreBulkAction::make()
            ->visible(fn (): bool => UserResource::canRestoreAny());
    }

    /**
     * Действующие аккаунты в выборке не стираются: навсегда удаляется
     * только отключённый (User::booted, forceDeleting) — остальные
     * попадут в отчёт как не удалённые.
     */
    public static function forceDeleteBulk(): ForceDeleteBulkAction
    {
        return ForceDeleteBulkAction::make()
            // Записи — по одной, с событиями модели: запрос целиком
            // стёр бы и действующие аккаунты мимо проверки
            ->fetchSelectedRecords()
            ->modalDescription('Будут стёрты из базы только отключённые аккаунты из выбранных. Отменить нельзя.')
            ->visible(fn (): bool => UserResource::canForceDeleteAny());
    }

    private static function isSelf(User $record): bool
    {
        return $record->getKey() === Auth::id();
    }
}
