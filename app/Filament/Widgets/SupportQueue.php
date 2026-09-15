<?php

declare(strict_types=1);

namespace App\Filament\Widgets;

use App\Filament\Resources\Tickets\TicketResource;
use App\Models\Support\Ticket;
use App\Support\AdminAccess;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Table;
use Filament\Widgets\TableWidget;
use Illuminate\Support\Facades\Auth;

/**
 * Открытые обращения — стартовый экран поддержки.
 *
 * Свои сверху, потом ничьи, потом чужие: сначала то, за что отвечаешь
 * лично, но ничьё обращение тоже должно попадаться на глаза — иначе
 * оно пролежит до первого распределения.
 *
 * Внутри каждой группы срочные вперёд, дальше по давности.
 */
class SupportQueue extends TableWidget
{
    protected static ?int $sort = -27;

    protected int|string|array $columnSpan = 'full';

    public static function canView(): bool
    {
        return AdminAccess::allows('support.view');
    }

    public function table(Table $table): Table
    {
        return $table
            ->heading('Открытые обращения')
            ->description('Ваши сверху, за ними ничьи')
            ->query(
                Ticket::query()
                    ->open()
                    ->with(['user', 'company', 'assignee'])
                    // Своё, ничьё, чужое — именно в таком порядке
                    ->orderByRaw('case when assignee_id = ? then 0 when assignee_id is null then 1 else 2 end', [Auth::id()])
                    ->orderByRaw("case priority when 'high' then 0 when 'normal' then 1 else 2 end")
                    ->orderBy('created_at'),
            )
            ->defaultSort(null)
            ->paginated([5])
            ->columns([
                TextColumn::make('subject')
                    ->label('Тема')
                    ->wrap()
                    ->limit(60)
                    ->description(fn (Ticket $record): string => $record->author()),

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
                    ->color('warning'),

                TextColumn::make('assignee.name')
                    ->label('Ведёт')
                    ->placeholder('никто'),

                TextColumn::make('created_at')
                    ->label('Ждёт')
                    ->state(fn (Ticket $record): string => $record->created_at->diffForHumans(syntax: true))
                    ->color(fn (Ticket $record): string => $record->created_at->diffInHours() >= 24 ? 'danger' : 'gray'),
            ])
            ->recordUrl(fn (Ticket $record): string => TicketResource::getUrl('edit', ['record' => $record]))
            ->emptyStateHeading('Открытых обращений нет')
            ->emptyStateDescription('Всё разобрано.');
    }
}
