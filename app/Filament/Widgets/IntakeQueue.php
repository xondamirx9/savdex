<?php

declare(strict_types=1);

namespace App\Filament\Widgets;

use App\Filament\Resources\Companies\CompanyResource;
use App\Models\Company;
use App\Support\AdminAccess;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Table;
use Filament\Widgets\TableWidget;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Support\Facades\Auth;

/**
 * Новые компании — стартовый экран менеджеров направлений.
 *
 * Менеджер поставщиков видит поставщиков, менеджер покупателей —
 * покупателей, суперадмин — и тех и других. Роль решает, чей это
 * экран: заводить два почти одинаковых виджета ради одного условия
 * незачем.
 *
 * Свежие сверху — здесь, в отличие от лидов, важна скорость первого
 * касания: компания, зарегистрировавшаяся утром, вечером уже смотрит
 * на конкурентов.
 */
class IntakeQueue extends TableWidget
{
    protected static ?int $sort = -28;

    protected int|string|array $columnSpan = 'full';

    public static function canView(): bool
    {
        return self::role() !== null || (Auth::user()?->isSuperadmin() ?? false);
    }

    /** Чьё это направление: supplier, buyer или ничьё. */
    private static function role(): ?string
    {
        $user = Auth::user();

        return match ($user?->admin_role) {
            AdminAccess::SUPPLIER_MANAGER => 'supplier',
            AdminAccess::BUYER_MANAGER => 'buyer',
            default => null,
        };
    }

    public function table(Table $table): Table
    {
        $role = self::role();

        return $table
            ->heading(match ($role) {
                'supplier' => 'Новые поставщики',
                'buyer' => 'Новые покупатели',
                default => 'Новые компании',
            })
            ->description('Зарегистрировались за последние две недели')
            ->query(
                Company::query()
                    // «both» тоже наш: компания, которая и продаёт,
                    // и закупает, нужна обоим менеджерам. У суперадмина
                    // направления нет — он смотрит за обоими сразу
                    ->when($role !== null, fn (Builder $query): Builder => $query
                        ->whereIn('primary_role', [$role, 'both']))
                    ->where('created_at', '>=', now()->subWeeks(2))
                    ->with(['country', 'city']),
            )
            ->defaultSort('created_at', 'desc')
            ->paginated([5])
            ->columns([
                TextColumn::make('name')
                    ->label('Компания')
                    ->wrap()
                    ->limit(50)
                    ->description(fn (Company $record): ?string => $record->city?->name ?? $record->country?->name),

                TextColumn::make('primary_role')
                    ->label('Направление')
                    ->badge()
                    ->formatStateUsing(fn (string $state): string => match ($state) {
                        'supplier' => 'Поставщик',
                        'buyer' => 'Покупатель',
                        default => 'И то и другое',
                    })
                    ->color('gray')
                    // Менеджеру направления колонка не нужна: у него
                    // в списке и так только его компании
                    ->visible(fn (): bool => self::role() === null),

                TextColumn::make('verification_level')
                    ->label('Проверка')
                    ->badge()
                    ->formatStateUsing(fn (int $state): string => match (true) {
                        $state >= 2 => 'Проверена+',
                        $state === 1 => 'Проверена',
                        default => 'Не проверена',
                    })
                    ->color(fn (int $state): string => $state > 0 ? 'success' : 'gray'),

                TextColumn::make('phone')
                    ->label('Телефон')
                    ->copyable()
                    ->placeholder('не указан'),

                TextColumn::make('created_at')
                    ->label('Появилась')
                    ->state(fn (Company $record): string => $record->created_at->diffForHumans(syntax: true)),
            ])
            ->recordUrl(fn (Company $record): string => CompanyResource::getUrl('edit', ['record' => $record]))
            ->emptyStateHeading(match ($role) {
                'supplier' => 'Новых поставщиков нет',
                'buyer' => 'Новых покупателей нет',
                default => 'Новых компаний нет',
            })
            ->emptyStateDescription('За две недели никто не зарегистрировался.');
    }
}
