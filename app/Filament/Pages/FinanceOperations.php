<?php

declare(strict_types=1);

namespace App\Filament\Pages;

use App\Models\WalletTransaction;
use App\Support\AdminAccess;
use BackedEnum;
use Filament\Pages\Page;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Columns\Summarizers\Sum;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Concerns\InteractsWithTable;
use Filament\Tables\Contracts\HasTable;
use Filament\Tables\Filters\Filter;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;
use UnitEnum;

/**
 * Финансовые операции — движения по кошелькам компаний.
 *
 * Отдельная страница, а не ресурс: движение по кошельку не создают и
 * не правят руками. Оно появляется как след покупки, списания или
 * возврата, и единственное, что с ним делают, — читают.
 *
 * Здесь закрывается спор «у меня списали лишнее»: остаток обязан быть
 * выводим из истории, и история должна быть видна целиком.
 */
class FinanceOperations extends Page implements HasTable
{
    use InteractsWithTable;

    public static function canAccess(): bool
    {
        return AdminAccess::allows('refunds.view');
    }

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedArrowsRightLeft;

    protected static ?string $navigationLabel = 'Финансовые операции';

    protected static string|UnitEnum|null $navigationGroup = 'Монетизация';

    protected static ?int $navigationSort = 4;

    protected string $view = 'filament.pages.finance-operations';

    public function getTitle(): string
    {
        return 'Финансовые операции';
    }

    public function getSubheading(): ?string
    {
        return 'Движения по кошелькам компаний: начисления, списания и возвраты. Записи не правятся — история должна сходиться.';
    }

    /** @var array<string, string> */
    private const REASONS = [
        'unlock' => 'Раскрытие контакта',
        'purchase' => 'Покупка',
        'refund' => 'Возврат',
        'complaint_refund' => 'Возврат по жалобе',
        'plan_grant' => 'Начисление по тарифу',
        'promotion' => 'Продвижение',
    ];

    public function table(Table $table): Table
    {
        return $table
            ->query(WalletTransaction::query()->with(['company', 'user']))
            ->defaultSort('created_at', 'desc')
            ->columns([
                TextColumn::make('created_at')
                    ->label('Когда')
                    ->dateTime('d.m.Y H:i')
                    ->sortable(),

                TextColumn::make('company.name')
                    ->label('Компания')
                    ->searchable()
                    ->placeholder('удалена'),

                TextColumn::make('kind')
                    ->label('Что')
                    ->badge()
                    ->color('gray')
                    ->formatStateUsing(fn (string $state): string => match ($state) {
                        'credits' => 'Кредиты',
                        'promo_units' => 'Продвижение',
                        default => $state,
                    }),

                TextColumn::make('amount')
                    ->label('Сколько')
                    ->alignEnd()
                    ->sortable()
                    // Знак — главное в этой колонке: начисление и списание
                    // различаются только им, и перепутать их дорого
                    ->formatStateUsing(fn (int $state): string => ($state > 0 ? '+' : '').number_format($state, 0, ',', ' '))
                    ->color(fn (int $state): string => $state > 0 ? 'success' : 'danger')
                    ->summarize(Sum::make()->label('Итого')->numeric(decimalPlaces: 0)),

                TextColumn::make('balance_after')
                    ->label('Остаток после')
                    ->alignEnd()
                    ->numeric(decimalPlaces: 0),

                TextColumn::make('reason')
                    ->label('Основание')
                    ->badge()
                    ->color('info')
                    ->formatStateUsing(fn (string $state): string => self::REASONS[$state] ?? $state),

                TextColumn::make('user.name')
                    ->label('Кто провёл')
                    ->placeholder('автоматически')
                    ->toggleable(),

                TextColumn::make('comment')
                    ->label('Комментарий')
                    ->wrap()
                    ->limit(60)
                    ->toggleable()
                    ->placeholder('—'),
            ])
            ->filters([
                SelectFilter::make('reason')
                    ->label('Основание')
                    ->options(self::REASONS),

                SelectFilter::make('kind')
                    ->label('Что')
                    ->options(['credits' => 'Кредиты', 'promo_units' => 'Продвижение']),

                Filter::make('grants')
                    ->label('Только начисления')
                    ->query(fn (Builder $query): Builder => $query->where('amount', '>', 0)),

                Filter::make('spends')
                    ->label('Только списания')
                    ->query(fn (Builder $query): Builder => $query->where('amount', '<', 0)),

                Filter::make('month')
                    ->label('За месяц')
                    ->query(fn (Builder $query): Builder => $query->where('created_at', '>=', now()->subMonth())),
            ])
            ->recordActions([])
            ->toolbarActions([])
            ->emptyStateHeading('Операций нет')
            ->emptyStateDescription('Сюда попадают начисления, списания и возвраты по кошелькам компаний.');
    }
}
