<?php

declare(strict_types=1);

namespace App\Filament\Resources\Leads\Tables;

use App\Models\Crm\Deal;
use App\Models\Crm\Lead;
use App\Support\AdminAccess;
use App\Support\AdminLog;
use Filament\Actions\Action;
use Filament\Actions\BulkActionGroup;
use Filament\Actions\DeleteAction;
use Filament\Actions\DeleteBulkAction;
use Filament\Actions\EditAction;
use Filament\Notifications\Notification;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\Filter;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Support\Facades\Auth;

/**
 * Лиды: очередь обращений.
 *
 * По умолчанию видно только открытые — закрытые лиды не ждут действий
 * и в рабочем списке только мешают. Новые сверху: остывший лид стоит
 * дешевле свежего.
 */
class LeadsTable
{
    /** @var array<string, string> */
    private const TONE = [
        Lead::STATUS_NEW => 'warning',
        Lead::STATUS_WORKING => 'info',
        Lead::STATUS_QUALIFIED => 'primary',
        Lead::STATUS_CONVERTED => 'success',
        Lead::STATUS_LOST => 'gray',
    ];

    public static function configure(Table $table): Table
    {
        return $table
            ->modifyQueryUsing(fn (Builder $query): Builder => $query->with(['company', 'contact', 'owner']))
            ->defaultSort('created_at', 'desc')
            ->columns([
                TextColumn::make('title')
                    ->label('Обращение')
                    ->searchable()
                    ->wrap()
                    ->limit(70)
                    ->description(fn (Lead $r): string => Lead::SOURCES[$r->source] ?? $r->source),

                TextColumn::make('contact_name')
                    ->label('Кто')
                    ->searchable()
                    ->state(fn (Lead $r): string => $r->contactName() ?? '—')
                    ->description(fn (Lead $r): ?string => $r->company?->name),

                TextColumn::make('contact_phone')
                    ->label('Телефон')
                    ->state(fn (Lead $r): ?string => $r->contact?->phone ?? $r->contact_phone)
                    ->copyable()
                    ->placeholder('—'),

                TextColumn::make('status')
                    ->label('Статус')
                    ->badge()
                    ->state(fn (Lead $r): string => $r->statusLabel())
                    ->color(fn (Lead $r): string => self::TONE[$r->status] ?? 'gray'),

                TextColumn::make('owner.name')
                    ->label('Ответственный')
                    ->placeholder('не распределён')
                    ->sortable(),

                TextColumn::make('created_at')
                    ->label('Пришёл')
                    ->dateTime('d.m.Y H:i')
                    ->sortable()
                    ->description(fn (Lead $r): string => $r->created_at->diffForHumans()),
            ])
            ->filters([
                Filter::make('open')
                    ->label('Только в работе')
                    ->default()
                    ->query(fn (Builder $query): Builder => $query->open()),

                SelectFilter::make('status')
                    ->label('Статус')
                    ->options(Lead::STATUSES),

                SelectFilter::make('source')
                    ->label('Источник')
                    ->options(Lead::SOURCES),

                Filter::make('mine')
                    ->label('Мои')
                    ->query(fn (Builder $query): Builder => $query->where('owner_id', Auth::id())),

                Filter::make('unassigned')
                    ->label('Нераспределённые')
                    ->query(fn (Builder $query): Builder => $query->whereNull('owner_id')),
            ])
            ->recordActions([
                /*
                 * «Взять себе» одной кнопкой.
                 *
                 * Открыть форму, найти поле, выбрать себя, сохранить —
                 * четыре действия там, где нужно одно, и потому лид
                 * возьмут не сразу.
                 */
                Action::make('claim')
                    ->label('Взять себе')
                    ->icon('heroicon-o-hand-raised')
                    ->color('primary')
                    ->visible(fn (Lead $r): bool => $r->owner_id === null && AdminAccess::allows('leads.edit'))
                    ->action(function (Lead $record): void {
                        $record->forceFill([
                            'owner_id' => Auth::id(),
                            'status' => $record->status === Lead::STATUS_NEW
                                ? Lead::STATUS_WORKING
                                : $record->status,
                        ])->save();

                        Notification::make()->title('Лид закреплён за вами')->success()->send();
                    }),

                /*
                 * Превращение лида в сделку.
                 *
                 * Переносит компанию, контакт и ответственного: заводить
                 * сделку заново значит потерять половину данных и связь
                 * с обращением, из которого она выросла.
                 */
                Action::make('convert')
                    ->label('В сделку')
                    ->icon('heroicon-o-arrow-right-circle')
                    ->color('success')
                    ->requiresConfirmation()
                    ->modalDescription('Лид получит статус «Стал сделкой». Компания, контакт и ответственный перенесутся в новую сделку.')
                    ->visible(fn (Lead $r): bool => $r->status !== Lead::STATUS_CONVERTED
                        && $r->status !== Lead::STATUS_LOST
                        && AdminAccess::allows('deals.create'))
                    ->action(function (Lead $record): void {
                        $deal = Deal::create([
                            'title' => $record->title,
                            'company_id' => $record->company_id,
                            'contact_id' => $record->contact_id,
                            'lead_id' => $record->id,
                            'owner_id' => $record->owner_id ?? Auth::id(),
                            'stage' => Deal::STAGE_NEW,
                        ]);

                        $record->forceFill(['status' => Lead::STATUS_CONVERTED])->save();

                        AdminLog::record('created', 'deals', $deal, note: 'Из лида №'.$record->id);

                        Notification::make()
                            ->title('Сделка создана')
                            ->body('Сумму и этап заполните в разделе «Сделки».')
                            ->success()
                            ->send();
                    }),

                EditAction::make(),
                DeleteAction::make(),
            ])
            ->toolbarActions([
                BulkActionGroup::make([
                    DeleteBulkAction::make()
                        ->visible(fn (): bool => AdminAccess::allows('leads.delete')),
                ]),
            ])
            ->emptyStateHeading('Лидов нет')
            ->emptyStateDescription('Сюда попадают обращения: заявки с сайта, звонки, письма и холодные контакты.');
    }
}
