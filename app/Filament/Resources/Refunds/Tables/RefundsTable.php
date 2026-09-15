<?php

declare(strict_types=1);

namespace App\Filament\Resources\Refunds\Tables;

use App\Models\Payment;
use App\Models\Refund;
use App\Services\Payments\RefundService;
use App\Support\AdminAccess;
use Filament\Actions\Action;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\Textarea;
use Filament\Forms\Components\TextInput;
use Filament\Notifications\Notification;
use Filament\Tables\Columns\Summarizers\Sum;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\Filter;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Support\Facades\Auth;
use Throwable;

/**
 * Возвраты: что заявлено и что проведено.
 *
 * Заявленные сверху: это деньги, по которым решение ещё не принято,
 * и каждый день ожидания клиент считает своим.
 */
class RefundsTable
{
    /** Формулировка решения обязательна: возврат без причины не объяснить проверяющему. */
    private static function noteField(string $label, bool $required): Textarea
    {
        return Textarea::make('note')
            ->label($label)
            ->rows(3)
            ->required($required)
            ->minLength($required ? 10 : 0);
    }

    public static function configure(Table $table): Table
    {
        return $table
            ->modifyQueryUsing(fn (Builder $query): Builder => $query
                ->with(['payment', 'company', 'author', 'decidedBy']))
            ->defaultSort('created_at', 'desc')
            ->columns([
                TextColumn::make('created_at')
                    ->label('Заявлен')
                    ->dateTime('d.m.Y H:i')
                    ->sortable()
                    ->description(fn (Refund $record): string => $record->created_at->diffForHumans()),

                TextColumn::make('company.name')
                    ->label('Компания')
                    ->searchable()
                    ->placeholder('удалена')
                    ->description(fn (Refund $record): ?string => $record->payment?->number),

                TextColumn::make('amount')
                    ->label('Сумма')
                    ->state(fn (Refund $record): string => $record->money())
                    ->alignEnd()
                    ->sortable()
                    ->summarize(Sum::make()->label('Итого')->numeric(decimalPlaces: 0))
                    // Видно, часть это или весь счёт: по частичному
                    // возврату счёт остаётся оплаченным
                    ->description(fn (Refund $record): ?string => $record->payment !== null
                        && $record->amount < $record->payment->amount
                            ? 'частичный'
                            : null),

                TextColumn::make('reason')
                    ->label('Причина')
                    ->wrap()
                    ->limit(70),

                TextColumn::make('status')
                    ->label('Решение')
                    ->badge()
                    ->state(fn (Refund $record): string => $record->statusLabel())
                    ->color(fn (Refund $record): string => match ($record->status) {
                        Refund::STATUS_DONE => 'success',
                        Refund::STATUS_REJECTED => 'gray',
                        default => 'warning',
                    })
                    ->description(fn (Refund $record): ?string => $record->decidedBy?->name),

                TextColumn::make('author.name')
                    ->label('Заявил')
                    ->toggleable()
                    ->placeholder('—'),
            ])
            ->filters([
                Filter::make('requested')
                    ->label('Ждут решения')
                    ->default()
                    ->query(fn (Builder $query): Builder => $query->where('status', Refund::STATUS_REQUESTED)),

                SelectFilter::make('status')
                    ->label('Решение')
                    ->options(Refund::STATUSES),
            ])
            ->headerActions([
                Action::make('request')
                    ->label('Заявить возврат')
                    ->icon('heroicon-o-plus')
                    ->visible(fn (): bool => AdminAccess::allows('refunds.create'))
                    ->schema([
                        Select::make('payment_id')
                            ->label('По какому счёту')
                            ->options(fn (): array => Payment::query()
                                ->where('status', 'paid')
                                ->latest('paid_at')
                                ->limit(100)
                                ->with('company')
                                ->get()
                                ->mapWithKeys(fn (Payment $p): array => [
                                    $p->id => $p->number.' — '.($p->company?->name ?? 'компания удалена')
                                        .' — '.number_format($p->amount, 0, ',', ' ').' '.$p->currency,
                                ])
                                ->all())
                            ->searchable()
                            ->required()
                            ->live(),

                        TextInput::make('amount')
                            ->label('Сумма возврата')
                            ->numeric()
                            ->minValue(1)
                            ->required()
                            ->helperText('Не больше остатка по счёту: частичные возвраты складываются'),

                        Textarea::make('reason')
                            ->label('Причина')
                            ->required()
                            ->minLength(10)
                            ->rows(3)
                            ->helperText('Обязательно: возврат без причины невозможно ни проверить, ни объяснить'),
                    ])
                    ->action(function (array $data): void {
                        try {
                            app(RefundService::class)->request(
                                Payment::findOrFail($data['payment_id']),
                                Auth::user(),
                                (int) $data['amount'],
                                $data['reason'],
                            );

                            Notification::make()->title('Возврат заявлен')->success()->send();
                        } catch (Throwable $e) {
                            Notification::make()->title('Не получилось')->body($e->getMessage())->danger()->send();
                        }
                    }),
            ])
            ->recordActions([
                Action::make('approve')
                    ->label('Провести')
                    ->icon('heroicon-o-check')
                    ->color('success')
                    ->requiresConfirmation()
                    ->modalDescription('Счёт получит статус «Возвращён», если возвращается вся сумма. Отменить проведение нельзя — только оформить обратную операцию.')
                    ->visible(fn (Refund $record): bool => ! $record->isDecided() && AdminAccess::allows('refunds.edit'))
                    ->schema([self::noteField('Комментарий к решению', false)])
                    ->action(function (Refund $record, array $data): void {
                        try {
                            app(RefundService::class)->approve($record, Auth::user(), $data['note'] ?? null);

                            Notification::make()->title('Возврат проведён')->success()->send();
                        } catch (Throwable $e) {
                            Notification::make()->title('Не получилось')->body($e->getMessage())->danger()->send();
                        }
                    }),

                Action::make('reject')
                    ->label('Отклонить')
                    ->icon('heroicon-o-x-mark')
                    ->color('danger')
                    ->visible(fn (Refund $record): bool => ! $record->isDecided() && AdminAccess::allows('refunds.edit'))
                    ->schema([self::noteField('Почему отказ', true)])
                    ->action(function (Refund $record, array $data): void {
                        try {
                            app(RefundService::class)->reject($record, Auth::user(), $data['note']);

                            Notification::make()->title('Возврат отклонён')->success()->send();
                        } catch (Throwable $e) {
                            Notification::make()->title('Не получилось')->body($e->getMessage())->danger()->send();
                        }
                    }),
            ])
            ->toolbarActions([])
            ->emptyStateHeading('Возвратов нет')
            ->emptyStateDescription('Возврат заявляется по оплаченному счёту и требует причины.');
    }
}
