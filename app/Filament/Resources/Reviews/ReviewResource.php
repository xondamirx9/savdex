<?php

declare(strict_types=1);

namespace App\Filament\Resources\Reviews;

use App\Filament\Resources\Reviews\Pages\ListReviews;
use App\Filament\Resources\Reviews\Tables\ReviewsTable;
use App\Models\Review;
use BackedEnum;
use Filament\Resources\Resource;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Table;
use UnitEnum;

/**
 * Отзывы и споры по ним — работа модератора.
 *
 * Формы правки нет: модератор не переписывает чужие отзывы, он решает,
 * остаётся отзыв на витрине или скрывается. Оба решения — действия
 * в списке, и оба требуют формулировки, которую увидят стороны.
 */
class ReviewResource extends Resource
{
    protected static ?string $model = Review::class;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedChatBubbleLeftRight;

    protected static ?string $navigationLabel = 'Отзывы';

    protected static ?string $modelLabel = 'отзыв';

    protected static ?string $pluralModelLabel = 'отзывы';

    protected static string|UnitEnum|null $navigationGroup = 'Модерация';

    protected static ?int $navigationSort = 1;

    /**
     * Счётчик — всё, что ждёт решения: новые отзывы на премодерации
     * и споры по опубликованным. Остальные внимания не требуют.
     */
    public static function getNavigationBadge(): ?string
    {
        $count = Review::query()
            ->where(fn ($q) => $q
                ->where('status', Review::STATUS_MODERATION)
                ->orWhere('dispute_status', 'pending'))
            ->count();

        return $count > 0 ? (string) $count : null;
    }

    public static function getNavigationBadgeColor(): ?string
    {
        return 'warning';
    }

    public static function table(Table $table): Table
    {
        return ReviewsTable::configure($table);
    }

    public static function getPages(): array
    {
        return [
            'index' => ListReviews::route('/'),
        ];
    }
}
