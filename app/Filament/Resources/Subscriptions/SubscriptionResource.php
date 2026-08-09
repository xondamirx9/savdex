<?php

declare(strict_types=1);

namespace App\Filament\Resources\Subscriptions;

use App\Filament\Resources\Subscriptions\Pages\ListSubscriptions;
use App\Filament\Resources\Subscriptions\Tables\SubscriptionsTable;
use App\Models\Subscription;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;
use Illuminate\Support\Facades\Auth;
use UnitEnum;

/**
 * Подписки компаний: кто что купил и когда кончается.
 *
 * Формы создания и редактирования нет намеренно. Подписка — не набор
 * полей, а событие: смена тарифа закрывает прежнюю, начисляет промо
 * и обнуляет счётчик раскрытий. Правка plan_id прямо в таблице
 * пропустила бы всё это и оставила компанию с чужими лимитами.
 * Поэтому только действия «Назначить» и «Сменить или продлить»,
 * идущие через SubscriptionService.
 */
class SubscriptionResource extends Resource
{
    protected static ?string $model = Subscription::class;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedCreditCard;

    protected static ?string $navigationLabel = 'Подписки';

    protected static ?string $modelLabel = 'подписка';

    protected static ?string $pluralModelLabel = 'подписки';

    protected static string|UnitEnum|null $navigationGroup = 'Монетизация';

    protected static ?int $navigationSort = 2;

    /** Счётчик показывает платящих — то число, ради которого всё делалось. */
    public static function getNavigationBadge(): ?string
    {
        return (string) Subscription::query()->where('status', 'active')->count();
    }

    public static function canViewAny(): bool
    {
        return Auth::user()?->isSuperadmin() ?? false;
    }

    public static function table(Table $table): Table
    {
        return SubscriptionsTable::configure($table);
    }

    public static function getPages(): array
    {
        return [
            'index' => ListSubscriptions::route('/'),
        ];
    }
}
