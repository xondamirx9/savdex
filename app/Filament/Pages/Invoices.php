<?php

declare(strict_types=1);

namespace App\Filament\Pages;

use App\Models\Payment;
use App\Services\OrderService;
use BackedEnum;
use Filament\Actions\Action;
use Filament\Forms\Components\Textarea;
use Filament\Notifications\Notification;
use Filament\Pages\Page;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Concerns\InteractsWithTable;
use Filament\Tables\Contracts\HasTable;
use Filament\Tables\Filters\Filter;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Table;
use Illuminate\Support\Facades\Auth;
use UnitEnum;

/**
 * Счета: подтверждение оплаты.
 *
 * Оплата идёт переводом на расчётный счёт, поэтому зачисление
 * подтверждает человек: он видит поступление в банковской выписке
 * и отмечает счёт оплаченным. В этот момент — и только в этот —
 * подписка активируется, а кредиты падают на кошелёк.
 *
 * Подключится Payme или Click — подтверждение станет автоматическим
 * по колбэку провайдера, а этот экран останется для переводов
 * и разбора спорных случаев.
 */
class Invoices extends Page implements HasTable
{
    use InteractsWithTable;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedBanknotes;

    protected static ?string $navigationLabel = 'Счета и оплаты';

    protected static string|UnitEnum|null $navigationGroup = 'Монетизация';

    protected static ?int $navigationSort = 3;

    protected string $view = 'filament.pages.invoices';

    public function getTitle(): string
    {
        return 'Счета и оплаты';
    }

    /** Счётчик — неоплаченные: деньги, которые ещё не пришли. */
    public static function getNavigationBadge(): ?string
    {
        $count = Payment::where('status', 'pending')->count();

        return $count > 0 ? (string) $count : null;
    }

    public static function getNavigationBadgeColor(): ?string
    {
        return 'warning';
    }

    public function table(Table $table): Table
    {
        return $table
            ->query(Payment::query()->with(['company', 'plan', 'creditPack', 'confirmedBy']))
            ->columns([
                TextColumn::make('number')
                    ->label('Счёт')
                    ->searchable()
                    ->weight('bold')
                    ->description(fn (Payment $p): string => $p->created_at->translatedFormat('d.m.Y')),

                TextColumn::make('company.name')
                    ->label('Компания')
                    ->searchable()
                    ->description(fn (Payment $p): ?string => $p->company?->tin),

                TextColumn::make('description')->label('За что')->wrap(),

                TextColumn::make('amount')
                    ->label('Сумма')
                    ->state(fn (Payment $p): string => $p->amountLabel())
                    ->sortable(),

                TextColumn::make('status')
                    ->label('Статус')
                    ->badge()
                    ->formatStateUsing(fn (string $state): string => Payment::STATUSES[$state] ?? $state)
                    ->color(fn (string $state): string => match ($state) {
                        'paid' => 'success',
                        'pending' => 'warning',
                        default => 'gray',
                    })
                    ->description(fn (Payment $p): ?string => $p->confirmedBy?->name),

                TextColumn::make('paid_at')
                    ->label('Оплачен')
                    ->date('d.m.Y')
                    ->placeholder('—')
                    ->sortable(),
            ])
            ->defaultSort('created_at', 'desc')
            ->filters([
                Filter::make('unpaid')
                    ->label('Ждут оплаты')
                    ->default()
                    ->query(fn ($query) => $query->where('status', 'pending')),

                SelectFilter::make('status')->label('Статус')->options(Payment::STATUSES),

                SelectFilter::make('purpose')->label('За что')->options([
                    'subscription' => 'Тариф',
                    'credits' => 'Кредиты',
                    'promo_units' => 'Продвижение',
                ]),

                Filter::make('overdue')
                    ->label('Просрочены')
                    ->query(fn ($query) => $query->where('status', 'pending')
                        ->where('created_at', '<', now()->subDays(OrderService::EXPIRES_DAYS))),
            ])
            ->recordActions([
                Action::make('confirm')
                    ->label('Деньги пришли')
                    ->icon('heroicon-o-check-circle')
                    ->color('success')
                    ->visible(fn (Payment $p): bool => $p->isPending())
                    ->modalHeading('Подтвердить поступление?')
                    ->modalDescription(fn (Payment $p): string => "«{$p->description}» будет начислено компании немедленно: подписка активируется, кредиты лягут на кошелёк. Убедитесь, что {$p->amountLabel()} действительно поступили.")
                    ->schema([
                        Textarea::make('note')
                            ->label('Отметка для себя')
                            ->rows(2)
                            // Не обязательна: обычно достаточно самого факта,
                            // а требовать текст на каждой рутинной операции
                            // значит получать «ок» в каждой второй записи
                            ->helperText('Номер платёжного поручения или дата выписки. Компания этого не увидит.'),
                    ])
                    ->action(function (Payment $record, array $data): void {
                        $result = app(OrderService::class)->confirm($record, Auth::user(), $data['note'] ?? null);

                        Notification::make()
                            ->title($result['message'])
                            ->status($result['ok'] ? 'success' : 'warning')
                            ->send();
                    }),

                Action::make('cancel')
                    ->label('Отменить счёт')
                    ->icon('heroicon-o-x-circle')
                    ->color('danger')
                    ->visible(fn (Payment $p): bool => $p->isPending())
                    ->requiresConfirmation()
                    ->modalHeading('Отменить счёт?')
                    ->modalDescription('Счёт останется в списке со статусом «Отменён» — исчезнувший счёт выглядит как потерянный платёж.')
                    ->schema([
                        Textarea::make('note')->label('Причина')->rows(2),
                    ])
                    ->action(function (Payment $record, array $data): void {
                        app(OrderService::class)->cancel($record, Auth::user(), $data['note'] ?? null);

                        Notification::make()->title('Счёт отменён')->success()->send();
                    }),
            ])
            ->emptyStateHeading('Неоплаченных счетов нет')
            ->emptyStateDescription('Здесь появятся счета, выставленные компаниями. Снимите фильтр, чтобы увидеть оплаченные.');
    }
}
