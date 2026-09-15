<?php

declare(strict_types=1);

namespace App\Filament\Resources\AdminActions\Tables;

use App\Models\AdminAction;
use App\Support\AdminAccess;
use Filament\Actions\Action;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\Filter;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;

/**
 * Журнал действий: кто, когда, что и с чем.
 *
 * Свежее сверху: журнал читают, когда ищут недавнее — «кто вчера
 * разблокировал эту компанию». За прошлым годом идут с фильтром.
 *
 * Действий нет, кроме просмотра изменений: строка журнала — свидетельство,
 * а не запись, с которой что-то делают.
 */
class AdminActionsTable
{
    /** @var array<string, string> */
    private const TONE = [
        'created' => 'success',
        'approved' => 'success',
        'unblocked' => 'success',
        'restored' => 'success',
        'deleted' => 'danger',
        'rejected' => 'danger',
        'blocked' => 'danger',
        'revoked' => 'danger',
        'returned' => 'warning',
        'hidden' => 'warning',
        'granted' => 'info',
        'exported' => 'info',
        'imported' => 'info',
        'refunded' => 'warning',
        'paid' => 'success',
    ];

    public static function configure(Table $table): Table
    {
        return $table
            ->modifyQueryUsing(fn (Builder $query): Builder => $query->with('user'))
            ->defaultSort('created_at', 'desc')
            ->columns([
                TextColumn::make('created_at')
                    ->label('Когда')
                    ->dateTime('d.m.Y H:i')
                    ->sortable()
                    ->description(fn (AdminAction $record): string => $record->created_at->diffForHumans()),

                TextColumn::make('user_name')
                    ->label('Кто')
                    ->searchable()
                    // Роль на момент действия, а не нынешняя: сотрудника
                    // могли перевести, а вопрос всегда про тогда
                    ->description(fn (AdminAction $record): ?string => $record->user_role !== null
                        ? (AdminAccess::ROLES[$record->user_role] ?? $record->user_role)
                        : null),

                TextColumn::make('action')
                    ->label('Что сделал')
                    ->badge()
                    ->state(fn (AdminAction $record): string => $record->actionLabel())
                    ->color(fn (AdminAction $record): string => self::TONE[$record->action] ?? 'gray'),

                TextColumn::make('section')
                    ->label('Раздел')
                    ->badge()
                    ->color('gray')
                    ->state(fn (AdminAction $record): string => $record->sectionLabel()),

                TextColumn::make('subject_label')
                    ->label('С чем')
                    ->searchable()
                    ->wrap()
                    ->limit(60)
                    ->placeholder('—'),

                TextColumn::make('note')
                    ->label('Формулировка')
                    ->wrap()
                    ->limit(60)
                    ->toggleable()
                    ->placeholder('—'),

                TextColumn::make('ip')
                    ->label('Адрес')
                    ->toggleable(isToggledHiddenByDefault: true)
                    ->placeholder('—'),
            ])
            ->filters([
                SelectFilter::make('section')
                    ->label('Раздел')
                    ->options(AdminAccess::SECTIONS),

                SelectFilter::make('action')
                    ->label('Действие')
                    ->options(AdminAction::ACTIONS),

                SelectFilter::make('user_id')
                    ->label('Сотрудник')
                    ->relationship('user', 'name')
                    ->searchable(),

                Filter::make('today')
                    ->label('Только за сегодня')
                    ->query(fn (Builder $query): Builder => $query->whereDate('created_at', today())),
            ])
            ->recordActions([
                Action::make('changes')
                    ->label('Что изменилось')
                    ->icon('heroicon-o-eye')
                    ->modalHeading('Что изменилось')
                    ->modalSubmitAction(false)
                    ->modalCancelActionLabel('Закрыть')
                    ->visible(fn (AdminAction $record): bool => $record->changes !== null)
                    ->modalContent(fn (AdminAction $record) => view('filament.admin-action-changes', [
                        'before' => $record->changes['before'] ?? [],
                        'after' => $record->changes['after'] ?? [],
                    ])),
            ])
            ->toolbarActions([])
            ->emptyStateHeading('Записей нет')
            ->emptyStateDescription('Журнал заполняется сам: сюда попадают действия администраторов в панели.');
    }
}
