<?php

declare(strict_types=1);

namespace App\Filament\Resources\Subscriptions\Tables;

use App\Models\Company;
use App\Models\Plan;
use App\Models\Subscription;
use App\Services\SubscriptionService;
use Filament\Actions\Action;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\Textarea;
use Filament\Forms\Components\TextInput;
use Filament\Notifications\Notification;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\Filter;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Table;
use Illuminate\Support\Facades\Auth;

/**
 * Кто на каком тарифе (§6.2 ТЗ) и ручная выдача.
 *
 * Список отвечает на два вопроса, которые задают чаще всего:
 * «сколько компаний платит» и «когда у этой кончается». Поэтому срок
 * показан днями до конца, а не датой: дату приходится вычитать из
 * сегодняшней в уме.
 */
class SubscriptionsTable
{
    /**
     * Поля выдачи — общие для кнопки в шапке и продления в строке.
     *
     * @return array<int, mixed>
     */
    private static function grantFields(bool $withCompany): array
    {
        $company = $withCompany ? [
            Select::make('company_id')
                ->label('Компания')
                ->options(fn (): array => Company::query()->orderBy('name')->pluck('name', 'id')->all())
                ->searchable()
                ->required(),
        ] : [];

        return [
            ...$company,

            Select::make('plan_id')
                ->label('Тариф')
                ->options(fn (): array => Plan::query()->orderBy('sort')->pluck('name', 'id')->all())
                ->required(),

            TextInput::make('days')
                ->label('Срок, дней')
                ->numeric()
                ->minValue(0)
                ->placeholder('период тарифа')
                ->helperText('Пусто — период тарифа. Ноль — бессрочно'),

            Textarea::make('reason')
                ->label('Основание')
                ->required()
                ->rows(2)
                ->placeholder('Например: срочная дебиторка, оплата по счёту №142 ожидается до 05.08')
                ->helperText('Останется в карточке подписки. Через месяц никто не вспомнит, почему тариф выдали бесплатно'),
        ];
    }

    /** Пустое поле и ноль — разные вещи: первое «как в тарифе», второе «бессрочно». */
    private static function days(array $data): ?int
    {
        return $data['days'] === null || $data['days'] === '' ? null : (int) $data['days'];
    }

    public static function configure(Table $table): Table
    {
        return $table
            ->modifyQueryUsing(fn ($query) => $query->with(['company', 'plan', 'grantedBy']))
            ->headerActions([
                Action::make('grant')
                    ->label('Назначить тариф')
                    ->icon('heroicon-o-gift')
                    ->color('primary')
                    ->schema(self::grantFields(withCompany: true))
                    ->action(function (array $data): void {
                        $company = Company::findOrFail($data['company_id']);

                        app(SubscriptionService::class)->assign(
                            $company,
                            Plan::findOrFail($data['plan_id']),
                            days: self::days($data),
                            source: Subscription::SOURCE_MANUAL,
                            grantedBy: Auth::user(),
                            reason: $data['reason'],
                        );

                        Notification::make()
                            ->title("Тариф назначен компании «{$company->name}»")
                            ->success()
                            ->send();
                    }),
            ])
            ->columns([
                TextColumn::make('company.name')
                    ->label('Компания')
                    ->searchable()
                    ->sortable()
                    ->description(fn (Subscription $record): ?string => $record->company?->tin),

                TextColumn::make('plan.name')
                    ->label('Тариф')
                    ->badge()
                    ->color('primary')
                    ->sortable(),

                TextColumn::make('source')
                    ->label('Откуда')
                    ->badge()
                    ->formatStateUsing(fn (string $state): string => $state === Subscription::SOURCE_MANUAL ? 'Выдан вручную' : 'Оплачен')
                    ->color(fn (string $state): string => $state === Subscription::SOURCE_MANUAL ? 'warning' : 'success')
                    ->description(fn (Subscription $record): ?string => $record->isManual()
                        ? ($record->grantedBy?->name ?? 'администратор').': '.($record->grant_reason ?? '—')
                        : null)
                    ->wrap(),

                TextColumn::make('status')
                    ->label('Статус')
                    ->badge()
                    ->formatStateUsing(fn (string $state): string => match ($state) {
                        'active' => 'Активна',
                        'cancelled' => 'Отменена',
                        default => 'Истекла',
                    })
                    ->color(fn (string $state): string => match ($state) {
                        'active' => 'success',
                        'cancelled' => 'gray',
                        default => 'danger',
                    }),

                TextColumn::make('ends_at')
                    ->label('Осталось')
                    ->state(function (Subscription $record): string {
                        if ($record->status !== 'active') {
                            return '—';
                        }

                        $left = $record->daysLeft();

                        return $left === null ? 'бессрочно' : "{$left} дн.";
                    })
                    ->description(fn (Subscription $record): ?string => $record->ends_at?->translatedFormat('d.m.Y'))
                    // Скоро истекающие подписки — повод позвонить,
                    // поэтому они выделены цветом, а не спрятаны в дату
                    ->color(fn (Subscription $record): string => $record->status === 'active'
                        && $record->daysLeft() !== null
                        && $record->daysLeft() <= 7 ? 'danger' : 'gray')
                    ->sortable(),

                TextColumn::make('started_at')
                    ->label('Начало')
                    ->date('d.m.Y')
                    ->sortable()
                    ->toggleable(isToggledHiddenByDefault: true),
            ])
            ->defaultSort('started_at', 'desc')
            ->filters([
                SelectFilter::make('plan_id')->label('Тариф')->relationship('plan', 'name'),

                SelectFilter::make('status')->label('Статус')->options([
                    'active' => 'Активна',
                    'expired' => 'Истекла',
                    'cancelled' => 'Отменена',
                ]),

                SelectFilter::make('source')->label('Откуда')->options([
                    Subscription::SOURCE_PAYMENT => 'Оплачен',
                    Subscription::SOURCE_MANUAL => 'Выдан вручную',
                ]),

                Filter::make('expiring')
                    ->label('Истекают в ближайшую неделю')
                    ->query(fn ($query) => $query->where('status', 'active')
                        ->whereNotNull('ends_at')
                        ->whereBetween('ends_at', [now(), now()->addDays(7)])),
            ])
            ->recordActions([
                Action::make('extend')
                    ->label('Сменить или продлить')
                    ->icon('heroicon-o-arrow-path')
                    ->color('warning')
                    ->schema(self::grantFields(withCompany: false))
                    ->fillForm(fn (Subscription $record): array => ['plan_id' => $record->plan_id])
                    ->action(function (Subscription $record, array $data): void {
                        $company = $record->company;

                        if ($company === null) {
                            Notification::make()->title('Компания удалена')->danger()->send();

                            return;
                        }

                        app(SubscriptionService::class)->assign(
                            $company,
                            Plan::findOrFail($data['plan_id']),
                            days: self::days($data),
                            source: Subscription::SOURCE_MANUAL,
                            grantedBy: Auth::user(),
                            reason: $data['reason'],
                        );

                        Notification::make()->title('Подписка обновлена')->success()->send();
                    }),

                Action::make('cancel')
                    ->label('Отменить')
                    ->icon('heroicon-o-x-circle')
                    ->color('danger')
                    ->visible(fn (Subscription $record): bool => $record->status === 'active')
                    ->requiresConfirmation()
                    ->modalHeading('Отменить подписку?')
                    ->modalDescription('Компания сразу перейдёт на Free: лимиты объявлений и раскрытий станут бесплатными. Опубликованные объявления останутся.')
                    ->action(function (Subscription $record): void {
                        $record->forceFill([
                            'status' => 'cancelled',
                            'cancelled_at' => now(),
                            'auto_renew' => false,
                        ])->save();

                        Notification::make()->title('Подписка отменена')->success()->send();
                    }),
            ])
            ->emptyStateHeading('Подписок нет')
            ->emptyStateDescription('Все компании на Free. Тариф можно назначить вручную кнопкой сверху.');
    }
}
