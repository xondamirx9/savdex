<?php

declare(strict_types=1);

namespace App\Filament\Resources\Users\Tables;

use App\Filament\Exports\UserExporter;
use App\Models\ActivityEvent;
use App\Models\User;
use App\Support\Notifier;
use Filament\Actions\Action;
use Filament\Actions\BulkActionGroup;
use Filament\Actions\DeleteBulkAction;
use Filament\Actions\EditAction;
use Filament\Actions\ExportAction;
use Filament\Actions\Exports\Enums\ExportFormat;
use Filament\Notifications\Notification;
use Filament\Tables\Columns\IconColumn;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Filters\TernaryFilter;
use Filament\Tables\Filters\TrashedFilter;
use Filament\Tables\Table;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\Str;

/**
 * Пользователи и ручная выдача доступов (§6.3 ТЗ).
 *
 * Пароль показывается администратору ровно один раз — при создании
 * или сбросе. Хранить его в открытом виде негде и незачем: аккаунт
 * всё равно потребует смены пароля при первом входе.
 */
class UsersTable
{
    public static function configure(Table $table): Table
    {
        return $table
            ->modifyQueryUsing(fn ($query) => $query->with('company'))
            /*
             * Выгрузка и загрузка данных (§6.4 ТЗ). Файл готовится
             * в очереди: выгрузка десятков тысяч строк в запросе
             * упирается в таймаут, а заказчик видит только «ошибка».
             */
            ->headerActions([
                ExportAction::make()
                    ->label('Выгрузить')
                    ->exporter(UserExporter::class)
                    ->formats([ExportFormat::Xlsx, ExportFormat::Csv])
                    ->visible(fn (): bool => Auth::user()?->isSuperadmin() ?? false),
            ])
            ->columns([
                TextColumn::make('name')
                    ->label('Имя')
                    ->searchable()
                    ->description(fn (User $record): string => $record->email),

                TextColumn::make('company.name')
                    ->label('Компания')
                    ->searchable()
                    ->placeholder('без компании')
                    ->toggleable(),

                TextColumn::make('company_role')
                    ->label('Роль')
                    ->badge()
                    /*
                     * У колонки в базе стоит default 'owner', поэтому
                     * администратор без компании выглядел её владельцем.
                     * Роль есть только там, где есть компания.
                     */
                    ->state(fn (User $record): ?string => $record->company_id === null
                        ? null
                        : ($record->company_role === 'owner' ? 'Владелец' : 'Сотрудник'))
                    ->placeholder('—'),

                TextColumn::make('admin_role')
                    ->label('В админке')
                    ->badge()
                    ->state(fn (User $record): ?string => $record->adminRoleLabel())
                    ->color(fn (User $record): string => $record->isSuperadmin() ? 'danger' : 'warning')
                    ->placeholder('—')
                    ->toggleable(),

                IconColumn::make('email_verified_at')
                    ->label('Почта')
                    ->boolean()
                    ->trueIcon('heroicon-o-check-circle')
                    ->falseIcon('heroicon-o-clock')
                    ->getStateUsing(fn (User $record): bool => $record->email_verified_at !== null),

                TextColumn::make('status')
                    ->label('Статус')
                    ->badge()
                    ->formatStateUsing(fn (string $state): string => $state === 'active' ? 'Активен' : 'Заблокирован')
                    ->color(fn (string $state): string => $state === 'active' ? 'success' : 'danger'),

                TextColumn::make('last_login_at')
                    ->label('Был')
                    ->dateTime('d.m.Y H:i')
                    ->placeholder('ни разу')
                    ->sortable()
                    ->toggleable(),
            ])
            ->defaultSort('created_at', 'desc')
            ->filters([
                SelectFilter::make('status')->label('Статус')->options([
                    'active' => 'Активен',
                    'blocked' => 'Заблокирован',
                ]),
                TernaryFilter::make('is_admin')->label('Администратор'),
                TrashedFilter::make(),
            ])
            ->recordActions([
                EditAction::make(),

                /*
                 * Ручное подтверждение почты (§6.3 ТЗ).
                 *
                 * Нужно там, где письмо не доходит: корпоративная почта
                 * рубит рассылки, домен ещё не прогрет, человек ошибся
                 * в адресе и просит поменять. Без этого поддержке
                 * остаётся только просить регистрироваться заново.
                 *
                 * Право только у суперадмина: подтверждение снимает
                 * ограничение на публикацию и на раскрытие контактов,
                 * то есть открывает деньги. Модератору этого не даём —
                 * его дело содержание объявлений, а не доступы.
                 */
                Action::make('verifyEmail')
                    ->label('Подтвердить почту')
                    ->icon('heroicon-o-envelope-open')
                    ->color('success')
                    ->visible(fn (User $record): bool => $record->email_verified_at === null
                        && (Auth::user()?->isSuperadmin() ?? false))
                    ->requiresConfirmation()
                    ->modalHeading('Подтвердить почту вручную?')
                    ->modalDescription(fn (User $record): string => "Адрес {$record->email} будет считаться подтверждённым без письма. Пользователь сразу сможет публиковать объявления и открывать контакты. Убедитесь, что адрес принадлежит именно этому человеку.")
                    ->modalSubmitActionLabel('Да, подтвердить')
                    ->action(function (User $record): void {
                        $record->forceFill(['email_verified_at' => now()])->save();

                        // Событие в ленте компании: ручное подтверждение —
                        // то, о чём потом спрашивают «кто открыл доступ»
                        if ($record->company_id !== null) {
                            ActivityEvent::create([
                                'company_id' => $record->company_id,
                                'type' => 'system',
                                'tone' => 'success',
                                'message' => "Почта {$record->email} подтверждена администратором",
                            ]);
                        }

                        app(Notifier::class)->user(
                            $record,
                            'system',
                            'Почта подтверждена',
                            [
                                'body' => 'Администратор подтвердил ваш адрес вручную. Публикация объявлений и раскрытие контактов доступны.',
                                'tone' => 'success',
                            ],
                        );

                        Notification::make()
                            ->title('Почта подтверждена')
                            ->body($record->email)
                            ->success()
                            ->send();
                    }),

                /*
                 * Сброс пароля администратором. Флаг must_change_password
                 * обязателен: выданный вручную пароль знают двое, и до
                 * его замены доступ нельзя считать принадлежащим человеку.
                 */
                Action::make('resetPassword')
                    ->label('Выдать пароль')
                    ->icon('heroicon-o-key')
                    ->color('warning')
                    ->requiresConfirmation()
                    ->modalHeading('Выдать новый пароль?')
                    ->modalDescription('Текущий пароль перестанет работать. Новый нужно передать человеку лично — показан он будет один раз.')
                    ->action(function (User $record): void {
                        $password = Str::password(12, symbols: false);

                        $record->forceFill([
                            'password' => $password,
                            'must_change_password' => true,
                        ])->save();

                        Notification::make()
                            ->title('Пароль выдан')
                            ->body("Передайте лично: {$password}")
                            ->persistent()
                            ->warning()
                            ->send();
                    }),

                Action::make('toggleStatus')
                    ->label(fn (User $record): string => $record->status === 'active' ? 'Заблокировать' : 'Разблокировать')
                    ->icon('heroicon-o-no-symbol')
                    ->color('danger')
                    // Заблокировать себя — верный способ остаться без доступа
                    // к панели, из которой блокировку можно снять
                    ->visible(fn (User $record): bool => $record->id !== Auth::id())
                    ->requiresConfirmation()
                    ->action(function (User $record): void {
                        $record->forceFill([
                            'status' => $record->status === 'active' ? 'blocked' : 'active',
                        ])->save();

                        Notification::make()->title('Статус изменён')->success()->send();
                    }),
            ])
            ->toolbarActions([
                BulkActionGroup::make([
                    /*
                     * Ограничение суперадмином — прямо на действии:
                     * canDeleteAny ресурса массовые действия не прячет,
                     * и без visible() модератор мог удалять записи пачкой.
                     */
                    DeleteBulkAction::make()
                        ->visible(fn (): bool => Auth::user()?->isSuperadmin() ?? false),
                ]),
            ]);
    }
}
