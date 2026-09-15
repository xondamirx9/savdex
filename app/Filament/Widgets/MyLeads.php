<?php

declare(strict_types=1);

namespace App\Filament\Widgets;

use App\Filament\Resources\Leads\LeadResource;
use App\Models\Crm\Lead;
use App\Support\AdminAccess;
use App\Support\AdminScope;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Table;
use Filament\Widgets\TableWidget;

/**
 * Лиды, до которых ещё не дошли руки.
 *
 * Первое, что должен увидеть продавец, открыв панель. Свои и ничьи —
 * то же, что он видит в разделе лидов, но без лишнего клика и без
 * закрытых: на стартовом экране место только тому, что требует
 * действия сегодня.
 *
 * Старые сверху: остывший лид стоит дешевле свежего, и разбирать
 * очередь надо с хвоста.
 */
class MyLeads extends TableWidget
{
    protected static ?int $sort = -30;

    protected int|string|array $columnSpan = 'full';

    public static function canView(): bool
    {
        return AdminAccess::allows('leads.view');
    }

    public function table(Table $table): Table
    {
        return $table
            ->heading('Лиды в работе')
            ->description('Ваши и нераспределённые — те, что ждут звонка')
            ->query(
                AdminScope::apply(Lead::query(), 'leads', 'owner_id', orphansVisible: true)
                    ->open()
                    ->with(['company', 'contact', 'owner']),
            )
            ->defaultSort('created_at')
            ->paginated([5])
            ->columns([
                TextColumn::make('title')
                    ->label('Обращение')
                    ->wrap()
                    ->limit(60)
                    ->description(fn (Lead $record): string => Lead::SOURCES[$record->source] ?? $record->source),

                TextColumn::make('contact_name')
                    ->label('Кто')
                    ->state(fn (Lead $record): string => $record->contactName() ?? '—')
                    ->description(fn (Lead $record): ?string => $record->company?->name),

                TextColumn::make('status')
                    ->label('Статус')
                    ->badge()
                    ->state(fn (Lead $record): string => $record->statusLabel())
                    ->color(fn (Lead $record): string => $record->status === Lead::STATUS_NEW ? 'warning' : 'info'),

                TextColumn::make('owner.name')
                    ->label('Ответственный')
                    ->placeholder('не распределён'),

                TextColumn::make('created_at')
                    ->label('Ждёт')
                    // «3 дня» читается быстрее даты: важно не когда
                    // пришёл, а сколько уже лежит
                    ->state(fn (Lead $record): string => $record->created_at->diffForHumans(syntax: true))
                    ->color(fn (Lead $record): string => $record->created_at->diffInDays() >= 3 ? 'danger' : 'gray'),
            ])
            ->recordUrl(fn (Lead $record): string => LeadResource::getUrl('edit', ['record' => $record]))
            ->emptyStateHeading('Лидов в работе нет')
            ->emptyStateDescription('Новые обращения появятся здесь сами.');
    }
}
