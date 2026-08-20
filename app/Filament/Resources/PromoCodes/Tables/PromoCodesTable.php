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
                        TextInput::make('count')
                            ->label('Сколько кодов')
                            ->numeric()
                            ->default(10)
                            ->minValue(1)
                            ->maxValue(self::MAX_BATCH)
                            ->required(),

                        Select::make('plan_id')
                            ->label('Тариф')
                            ->options(fn (): array => Plan::query()
                                ->where('is_active', true)
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
                            ->required()
                            ->helperText('Сколько дней тарифа получит компания, активировавшая код'),

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
                    ->color('primary')
                    ->description(fn (PromoCode $r): string => "на {$r->days} дн."),

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

        for ($i = 0; $i < (int) $data['count']; $i++) {
            do {
                $code = PromoCode::generateCode($prefix);
            } while (PromoCode::query()->where('code', $code)->exists());

            PromoCode::create([
                'code' => $code,
                'plan_id' => (int) $data['plan_id'],
                'days' => (int) $data['days'],
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
