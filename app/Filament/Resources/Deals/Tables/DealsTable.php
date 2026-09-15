<?php

declare(strict_types=1);

namespace App\Filament\Resources\Deals\Tables;

use App\Models\Crm\Deal;
use App\Support\AdminAccess;
use Filament\Actions\BulkActionGroup;
use Filament\Actions\DeleteAction;
use Filament\Actions\DeleteBulkAction;
use Filament\Actions\EditAction;
use Filament\Tables\Columns\Summarizers\Sum;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\Filter;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Support\Facades\Auth;

/**
 * Сделки: что в работе и на какую сумму.
 *
 * По умолчанию открытые — закрытая сделка не требует действий. Под
 * колонкой суммы стоит итог: первый вопрос к списку сделок всегда
 * «сколько там всего».
 */
class DealsTable
{
    /** @var array<string, string> */
    private const TONE = [
        Deal::STAGE_NEW => 'gray',
        Deal::STAGE_NEGOTIATION => 'info',
        Deal::STAGE_PROPOSAL => 'warning',
        Deal::STAGE_WON => 'success',
        Deal::STAGE_LOST => 'danger',
    ];

    public static function configure(Table $table): Table
    {
        return $table
            ->modifyQueryUsing(fn (Builder $query): Builder => $query->with(['company', 'contact', 'owner']))
            ->defaultSort('expected_close_at')
            ->columns([
                TextColumn::make('title')
                    ->label('Сделка')
                    ->searchable()
                    ->wrap()
                    ->limit(60)
                    ->description(fn (Deal $r): ?string => $r->company?->name),

                TextColumn::make('amount')
                    ->label('Сумма')
                    ->state(fn (Deal $r): string => $r->money())
                    ->sortable()
                    ->alignEnd()
                    // Итог под колонкой: первый вопрос к списку сделок
                    // всегда «сколько там всего»
                    ->summarize(Sum::make()->label('Итого')->numeric(decimalPlaces: 0)),

                TextColumn::make('stage')
                    ->label('Этап')
                    ->badge()
                    ->state(fn (Deal $r): string => $r->stageLabel())
                    ->color(fn (Deal $r): string => self::TONE[$r->stage] ?? 'gray'),

                TextColumn::make('owner.name')
                    ->label('Ответственный')
                    ->sortable()
                    ->placeholder('—'),

                TextColumn::make('expected_close_at')
                    ->label('Ждём закрытия')
                    ->date('d.m.Y')
                    ->sortable()
                    ->placeholder('не указана')
                    // Просроченная дата у открытой сделки — сигнал, а не
                    // украшение: либо двигать срок, либо закрывать
                    ->color(fn (Deal $r): string => $r->closed_at === null
                        && $r->expected_close_at?->isPast()
                            ? 'danger'
                            : 'gray'),

                TextColumn::make('closed_at')
                    ->label('Закрыта')
                    ->dateTime('d.m.Y')
                    ->toggleable(isToggledHiddenByDefault: true)
                    ->placeholder('—'),
            ])
            ->filters([
                Filter::make('open')
                    ->label('Только в работе')
                    ->default()
                    ->query(fn (Builder $query): Builder => $query->open()),

                SelectFilter::make('stage')
                    ->label('Этап')
                    ->options(Deal::STAGES),

                Filter::make('mine')
                    ->label('Мои')
                    ->query(fn (Builder $query): Builder => $query->where('owner_id', Auth::id())),

                Filter::make('overdue')
                    ->label('Просроченные')
                    ->query(fn (Builder $query): Builder => $query->open()->whereDate('expected_close_at', '<', today())),
            ])
            ->recordActions([
                EditAction::make(),
                DeleteAction::make(),
            ])
            ->toolbarActions([
                BulkActionGroup::make([
                    DeleteBulkAction::make()
                        ->visible(fn (): bool => AdminAccess::allows('deals.delete')),
                ]),
            ])
            ->emptyStateHeading('Сделок нет')
            ->emptyStateDescription('Сделка заводится руками или вырастает из лида кнопкой «В сделку».');
    }
}
