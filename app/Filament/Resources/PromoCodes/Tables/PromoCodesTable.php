<?php

declare(strict_types=1);

namespace App\Filament\Resources\PromoCodes\Tables;

use App\Models\Plan;
use App\Models\PromoCode;
use Filament\Actions\Action;
use Filament\Actions\BulkAction;
use Filament\Forms\Components\DatePicker;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\TextInput;
use Filament\Notifications\Notification;
use Filament\Schemas\Components\Utilities\Get;
use Filament\Tables\Columns\IconColumn;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\Filter;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Collection;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Auth;

class PromoCodesTable
{
    /** Сколько кодов выпускают за раз: больше пачки трудно раздать. */
    private const MAX_BATCH = 500;

    public static function configure(Table $table): Table
    {
        return $table
            ->modifyQueryUsing(fn ($query) => $query->with(['plan', 'usedByCompany', 'createdBy']))
            ->headerActions([
                Action::make('issue')
                    ->label('Выпустить коды')
                    ->icon('heroicon-o-plus')
                    ->color('primary')
                    ->schema([
                        Select::make('kind')
                            ->label('Вид промокода')
                            ->options([
                                'free' => 'Бесплатный период — тариф выдаётся сразу, без оплаты',
                                'discount' => 'Скидка в процентах — остаток цены оплачивается онлайн',
                            ])
                            ->default('free')
                            ->required()
                            ->live(),

                        TextInput::make('count')
                            ->label('Сколько кодов')
                            ->numeric()
                            ->default(10)
                            ->minValue(1)
                            ->maxValue(self::MAX_BATCH)
                            ->required(),

                        Select::make('plan_id')
                            ->label('Тариф')
                            /*
                             * Бесплатный тариф из списка исключён для обоих
                             * видов: дарить его нечего (он и так у всех),
                             * а скидка от нулевой цены — счёт на ноль сумов.
                             */
                            ->options(fn (): array => Plan::query()
                                ->where('is_active', true)
                                ->where('code', '!=', Plan::FREE)
                                ->orderBy('sort')
                                ->pluck('name', 'id')
                                ->all())
                            ->default(fn (): ?int => Plan::query()->where('code', 'premium')->value('id'))
                            ->required(),

                        TextInput::make('days')
                            ->label('Срок доступа, дней')
                            ->numeric()
                            ->default(30)
                            ->minValue(1)
                            ->maxValue(365)
                            ->required(fn (Get $get): bool => $get('kind') === 'free')
                            ->visible(fn (Get $get): bool => $get('kind') === 'free')
                            ->helperText('Сколько дней тарифа получит компания, активировавшая код'),

                        TextInput::make('discount_percent')
                            ->label('Скидка, %')
                            ->numeric()
                            ->suffix('%')
                            ->default(30)
                            ->minValue(1)
                            ->maxValue(99)
                            ->required(fn (Get $get): bool => $get('kind') === 'discount')
                            ->visible(fn (Get $get): bool => $get('kind') === 'discount')
                            ->helperText('Активация выставит счёт на остаток цены тарифа и уведёт покупателя на онлайн-оплату (Uzum). Срок доступа — стандартный период тарифа'),

                        DatePicker::make('expires_at')
                            ->label('Активировать до (включительно)')
                            ->helperText('Пусто — код не сгорает. В указанный день код ещё работает, со следующего — нет'),

                        TextInput::make('prefix')
                            ->label('Префикс кода')
                            ->default('SVDX')
                            ->maxLength(8)
                            ->helperText('Видно в коде: SVDX-A7K2M9PQ. По нему в списке ищут коды одной акции'),

                        TextInput::make('note')
                            ->label('Для кого / повод')
                            ->maxLength(255)
                            ->placeholder('Например: выставка UzBuild, ноябрь')
                            ->helperText('Останется в списке рядом с кодом. Через месяц никто не вспомнит, куда ушла пачка'),
                    ])
                    ->action(function (array $data): void {
                        $codes = self::issue($data);

                        Notification::make()
                            ->title('Выпущено кодов: '.count($codes))
                            ->body('Скопируйте их из списка — код показывается полностью.')
                            ->success()
                            ->send();
                    }),
            ])
            ->columns([
                TextColumn::make('code')
                    ->label('Код')
                    ->searchable()
                    ->copyable()
                    ->copyMessage('Код скопирован')
                    ->weight('bold')
                    ->description(fn (PromoCode $r): ?string => $r->note),

                TextColumn::make('plan.name')
                    ->label('Тариф')
                    ->badge()
                    ->color(fn (PromoCode $r): string => $r->isDiscount() ? 'warning' : 'primary')
                    ->description(fn (PromoCode $r): string => $r->isDiscount()
                        ? "скидка {$r->discount_percent}%"
                        : "на {$r->days} дн. бесплатно"),

                TextColumn::make('used_at')
                    ->label('Активирован')
                    ->dateTime('d.m.Y H:i')
                    ->placeholder('—')
                    ->sortable()
                    ->description(fn (PromoCode $r): ?string => $r->usedByCompany?->name),

                TextColumn::make('expires_at')
                    ->label('Активировать до')
                    ->date('d.m.Y')
                    ->placeholder('бессрочно')
                    ->sortable()
                    // Просроченный код в списке должен читаться как нерабочий,
                    // а не как «дата в прошлом, ну и что»
                    ->color(fn (PromoCode $r): ?string => $r->isExpired() && ! $r->isUsed() ? 'danger' : null),

                IconColumn::make('is_active')->label('Действует')->boolean(),

                TextColumn::make('created_at')
                    ->label('Выпущен')
                    ->date('d.m.Y')
                    ->sortable()
                    ->toggleable(isToggledHiddenByDefault: true)
                    ->description(fn (PromoCode $r): ?string => $r->createdBy?->name),
            ])
            ->defaultSort('created_at', 'desc')
            ->filters([
                Filter::make('free')
                    ->label('Свободные')
                    ->query(fn ($query) => $query->redeemable()),

                Filter::make('used')
                    ->label('Активированные')
                    ->query(fn ($query) => $query->whereNotNull('used_at')),

                SelectFilter::make('plan_id')
                    ->label('Тариф')
                    ->options(fn (): array => Plan::query()->orderBy('sort')->pluck('name', 'id')->all()),

                Filter::make('discount')
                    ->label('Скидочные')
                    ->query(fn ($query) => $query->whereNotNull('discount_percent')),
            ])
            ->recordActions([
                Action::make('toggle')
                    ->label(fn (PromoCode $r): string => $r->is_active ? 'Отключить' : 'Включить')
                    ->icon(fn (PromoCode $r): string => $r->is_active ? 'heroicon-o-no-symbol' : 'heroicon-o-check')
                    ->color(fn (PromoCode $r): string => $r->is_active ? 'danger' : 'success')
                    // Погашенный код включать и выключать нечего:
                    // он уже сработал, и повторно не сработает
                    ->hidden(fn (PromoCode $r): bool => $r->isUsed())
                    ->requiresConfirmation()
                    ->action(fn (PromoCode $r) => $r->forceFill(['is_active' => ! $r->is_active])->save()),
            ])
            ->toolbarActions([
                BulkAction::make('disable')
                    ->label('Отключить выбранные')
                    ->icon('heroicon-o-no-symbol')
                    ->color('danger')
                    ->requiresConfirmation()
                    ->deselectRecordsAfterCompletion()
                    ->action(fn (Collection $records) => $records
                        ->filter(fn (PromoCode $r): bool => ! $r->isUsed())
                        ->each(fn (PromoCode $r) => $r->forceFill(['is_active' => false])->save())),
            ]);
    }

    /**
     * Выпуск пачки кодов.
     *
     * Совпадения обходятся повтором, а не игнорируются: молча выпустить
     * 9 кодов вместо 10 значит недодать один код тому, кому его обещали.
     *
     * @param  array<string, mixed>  $data
     * @return list<string>
     */
    private static function issue(array $data): array
    {
        $codes = [];
        $prefix = trim((string) ($data['prefix'] ?? 'SVDX'));

        /*
         * Конец дня, а не его начало: выбранная в календаре дата
         * приходит как «2026-12-31», и без этого код переставал
         * работать в полночь того самого дня, до которого он объявлен
         * действующим.
         */
        $expiresAt = ($data['expires_at'] ?? null) === null
            ? null
            : Carbon::parse((string) $data['expires_at'])->endOfDay();

        // У скидочного кода дни не заданы: срок доступа определит
        // стандартный период тарифа при оплате счёта
        $discount = ($data['kind'] ?? 'free') === 'discount';

        for ($i = 0; $i < (int) $data['count']; $i++) {
            do {
                $code = PromoCode::generateCode($prefix);
            } while (PromoCode::query()->where('code', $code)->exists());

            PromoCode::create([
                'code' => $code,
                'plan_id' => (int) $data['plan_id'],
                'days' => $discount ? 0 : (int) $data['days'],
                'discount_percent' => $discount ? (int) $data['discount_percent'] : null,
                'expires_at' => $expiresAt,
                'is_active' => true,
                'note' => $data['note'] ?? null,
                'created_by' => Auth::id(),
            ]);

            $codes[] = $code;
        }

        return $codes;
    }
}
