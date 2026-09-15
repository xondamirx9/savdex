<?php

declare(strict_types=1);

namespace App\Filament\Resources\Tickets\Tables;

use App\Models\Support\Message;
use App\Models\Support\Ticket;
use App\Support\AdminAccess;
use App\Support\AdminLog;
use Filament\Actions\Action;
use Filament\Actions\BulkActionGroup;
use Filament\Actions\DeleteAction;
use Filament\Actions\DeleteBulkAction;
use Filament\Actions\EditAction;
use Filament\Forms\Components\Checkbox;
use Filament\Forms\Components\Textarea;
use Filament\Notifications\Notification;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\Filter;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Support\Facades\Auth;

/**
 * Обращения: очередь поддержки.
 *
 * Срочные сверху, потом по давности: обращение, которое ждёт третий
 * день, важнее свежего, но авария важнее обоих.
 */
class TicketsTable
{
    /** @var array<string, string> */
    private const TONE = [
        Ticket::STATUS_OPEN => 'warning',
        Ticket::STATUS_WORKING => 'info',
        Ticket::STATUS_WAITING => 'gray',
        Ticket::STATUS_CLOSED => 'success',
    ];

    public static function configure(Table $table): Table
    {
        return $table
            ->modifyQueryUsing(fn (Builder $query): Builder => $query
                ->with(['user', 'company', 'assignee'])
                ->withCount('messages'))
            ->defaultSort('created_at', 'desc')
            ->columns([
                TextColumn::make('subject')
                    ->label('Тема')
                    ->searchable()
                    ->wrap()
                    ->limit(70)
                    ->description(fn (Ticket $record): string => Ticket::CHANNELS[$record->channel] ?? $record->channel),

                TextColumn::make('author_name')
                    ->label('Кто')
                    ->searchable()
                    ->state(fn (Ticket $record): string => $record->author())
                    ->description(fn (Ticket $record): ?string => $record->company?->name),

                TextColumn::make('priority')
                    ->label('Важность')
                    ->badge()
                    ->formatStateUsing(fn (string $state): string => Ticket::PRIORITIES[$state] ?? $state)
                    ->color(fn (string $state): string => match ($state) {
                        'high' => 'danger',
                        'low' => 'gray',
                        default => 'info',
                    }),

                TextColumn::make('status')
                    ->label('Статус')
                    ->badge()
                    ->state(fn (Ticket $record): string => $record->statusLabel())
                    ->color(fn (Ticket $record): string => self::TONE[$record->status] ?? 'gray'),

                TextColumn::make('assignee.name')
                    ->label('Ведёт')
                    ->placeholder('не назначен')
                    ->sortable(),

                TextColumn::make('messages_count')
                    ->label('Сообщений')
                    ->badge()
                    ->color('gray'),

                TextColumn::make('created_at')
                    ->label('Пришло')
                    ->dateTime('d.m.Y H:i')
                    ->sortable()
                    ->description(fn (Ticket $record): string => $record->created_at->diffForHumans()),
            ])
            ->filters([
                Filter::make('open')
                    ->label('Только открытые')
                    ->default()
                    ->query(fn (Builder $query): Builder => $query->open()),

                SelectFilter::make('status')
                    ->label('Статус')
                    ->options(Ticket::STATUSES),

                SelectFilter::make('priority')
                    ->label('Важность')
                    ->options(Ticket::PRIORITIES),

                Filter::make('mine')
                    ->label('Мои')
                    ->query(fn (Builder $query): Builder => $query->where('assignee_id', Auth::id())),

                Filter::make('unassigned')
                    ->label('Ничьи')
                    ->query(fn (Builder $query): Builder => $query->whereNull('assignee_id')),
            ])
            ->recordActions([
                Action::make('take')
                    ->label('Взять')
                    ->icon('heroicon-o-hand-raised')
                    ->color('primary')
                    ->visible(fn (Ticket $record): bool => $record->assignee_id === null
                        && AdminAccess::allows('support.edit'))
                    ->action(function (Ticket $record): void {
                        $record->forceFill([
                            'assignee_id' => Auth::id(),
                            'status' => $record->status === Ticket::STATUS_OPEN
                                ? Ticket::STATUS_WORKING
                                : $record->status,
                        ])->save();

                        Notification::make()->title('Обращение закреплено за вами')->success()->send();
                    }),

                /*
                 * Ответ и внутренняя заметка — одна форма с галочкой.
                 *
                 * Раздельные кнопки означали бы, что однажды нажмут не ту,
                 * и заметка о клиенте уедет клиенту. Галочка видна всё
                 * время, и её состояние написано словами.
                 */
                Action::make('reply')
                    ->label('Ответить')
                    ->icon('heroicon-o-chat-bubble-left-right')
                    ->visible(fn (): bool => AdminAccess::allows('support.edit'))
                    ->schema([
                        Textarea::make('body')
                            ->label('Текст')
                            ->required()
                            ->rows(6),

                        Checkbox::make('is_internal')
                            ->label('Внутренняя заметка — клиент её не увидит')
                            ->default(false),
                    ])
                    ->action(function (Ticket $record, array $data): void {
                        Message::create([
                            'ticket_id' => $record->id,
                            'author_id' => Auth::id(),
                            'from_staff' => true,
                            'is_internal' => (bool) ($data['is_internal'] ?? false),
                            'body' => $data['body'],
                        ]);

                        $internal = (bool) ($data['is_internal'] ?? false);

                        $record->forceFill([
                            'last_reply_at' => now(),
                            // Внутренняя заметка не меняет статус: клиент
                            // ничего не получил и ждать его нечего
                            'status' => $internal
                                ? $record->status
                                : Ticket::STATUS_WAITING,
                        ])->save();

                        AdminLog::record('updated', 'support', $record,
                            note: $internal ? 'Внутренняя заметка' : 'Ответ клиенту');

                        Notification::make()
                            ->title($internal ? 'Заметка сохранена' : 'Ответ отправлен')
                            ->success()
                            ->send();
                    }),

                Action::make('close')
                    ->label(fn (Ticket $record): string => $record->status === Ticket::STATUS_CLOSED
                        ? 'Открыть снова'
                        : 'Закрыть')
                    ->icon('heroicon-o-check-circle')
                    ->color(fn (Ticket $record): string => $record->status === Ticket::STATUS_CLOSED ? 'gray' : 'success')
                    ->visible(fn (): bool => AdminAccess::allows('support.edit'))
                    ->action(function (Ticket $record): void {
                        $record->forceFill([
                            'status' => $record->status === Ticket::STATUS_CLOSED
                                ? Ticket::STATUS_WORKING
                                : Ticket::STATUS_CLOSED,
                        ])->save();

                        Notification::make()->title('Статус изменён')->success()->send();
                    }),

                EditAction::make(),
                DeleteAction::make(),
            ])
            ->toolbarActions([
                BulkActionGroup::make([
                    DeleteBulkAction::make()
                        ->visible(fn (): bool => AdminAccess::allows('support.delete')),
                ]),
            ])
            ->emptyStateHeading('Обращений нет')
            ->emptyStateDescription('Сюда попадают вопросы клиентов: с формы на сайте, по почте и по телефону.');
    }
}
