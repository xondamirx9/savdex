<?php

declare(strict_types=1);

namespace App\Filament\Resources\PlatformReviews;

use App\Filament\Concerns\AuthorizesBySection;
use App\Filament\Resources\PlatformReviews\Pages\ListPlatformReviews;
use App\Models\PlatformReview;
use App\Services\PlatformReviewService;
use App\Support\AdminAccess;
use BackedEnum;
use Filament\Actions\Action;
use Filament\Forms\Components\Textarea;
use Filament\Notifications\Notification;
use Filament\Resources\Resource;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\Filter;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Table;
use Illuminate\Support\Facades\Auth;
use UnitEnum;

/**
 * Модерация отзывов о площадке.
 *
 * Право — то же, что на отзывы о компаниях (раздел «Отзывы»): это
 * одна работа одного модератора. Заводить или загружать отзывы
 * о площадке отсюда нельзя — их пишут только сами пользователи.
 */
class PlatformReviewResource extends Resource
{
    use AuthorizesBySection;

    protected static string $accessSection = 'reviews';

    protected static ?string $model = PlatformReview::class;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedStar;

    protected static ?string $navigationLabel = 'Отзывы о площадке';

    protected static ?string $modelLabel = 'отзыв о площадке';

    protected static ?string $pluralModelLabel = 'отзывы о площадке';

    protected static string|UnitEnum|null $navigationGroup = 'Модерация';

    protected static ?int $navigationSort = 2;

    public static function canCreate(): bool
    {
        return false;
    }

    public static function getNavigationBadge(): ?string
    {
        $count = PlatformReview::query()->where('status', PlatformReview::STATUS_MODERATION)->count();

        return $count > 0 ? (string) $count : null;
    }

    public static function getNavigationBadgeColor(): ?string
    {
        return 'warning';
    }

    private static function canDecide(): bool
    {
        return AdminAccess::allows('reviews.'.AdminAccess::EDIT);
    }

    public static function table(Table $table): Table
    {
        return $table
            ->modifyQueryUsing(fn ($query) => $query->with(['user', 'company', 'moderator']))
            ->columns([
                TextColumn::make('user.name')
                    ->label('Автор')
                    ->placeholder('учётная запись удалена')
                    ->description(fn (PlatformReview $r): ?string => $r->company?->name)
                    ->searchable(),

                TextColumn::make('rating')
                    ->label('Оценка')
                    ->badge()
                    ->formatStateUsing(fn (int $state): string => "{$state} из 5")
                    ->color(fn (int $state): string => match (true) {
                        $state >= 4 => 'success',
                        $state === 3 => 'warning',
                        default => 'danger',
                    })
                    ->sortable(),

                TextColumn::make('body')->label('Отзыв')->wrap()->limit(160)->searchable(),

                TextColumn::make('status')
                    ->label('На витрине')
                    ->badge()
                    ->formatStateUsing(fn (string $state): string => match ($state) {
                        PlatformReview::STATUS_PUBLISHED => 'Виден',
                        PlatformReview::STATUS_MODERATION => 'Ждёт проверки',
                        default => 'Скрыт',
                    })
                    ->color(fn (string $state): string => match ($state) {
                        PlatformReview::STATUS_PUBLISHED => 'success',
                        PlatformReview::STATUS_MODERATION => 'warning',
                        default => 'gray',
                    })
                    // Что насторожило автоматическую проверку — под статусом
                    ->description(fn (PlatformReview $r): ?string => $r->screening_flags ?? $r->moderator_note)
                    ->wrap(),

                TextColumn::make('updated_at')->label('Отправлен')->date('d.m.Y')->sortable(),

                TextColumn::make('moderated_at')
                    ->label('Решение')
                    ->date('d.m.Y')
                    ->description(fn (PlatformReview $r): ?string => $r->moderator?->name)
                    ->placeholder('—')
                    ->toggleable(isToggledHiddenByDefault: true),
            ])
            ->defaultSort('updated_at', 'desc')
            ->filters([
                Filter::make('waiting')
                    ->label('Ждут решения')
                    ->default()
                    ->query(fn ($query) => $query->where('status', PlatformReview::STATUS_MODERATION)),

                SelectFilter::make('status')->label('На витрине')->options([
                    PlatformReview::STATUS_PUBLISHED => 'Виден',
                    PlatformReview::STATUS_MODERATION => 'Ждёт проверки',
                    PlatformReview::STATUS_HIDDEN => 'Скрыт',
                ]),

                SelectFilter::make('rating')->label('Оценка')->options([5 => '5', 4 => '4', 3 => '3', 2 => '2', 1 => '1']),
            ])
            ->recordActions([
                Action::make('approve')
                    ->label('Опубликовать')
                    ->icon('heroicon-o-check-badge')
                    ->color('success')
                    ->visible(fn (PlatformReview $r): bool => self::canDecide() && $r->status === PlatformReview::STATUS_MODERATION)
                    ->requiresConfirmation()
                    ->modalHeading('Опубликовать отзыв?')
                    ->modalDescription('Отзыв появится на странице «Отзывы» и может попасть на главную. Автор получит уведомление.')
                    ->action(function (PlatformReview $record): void {
                        app(PlatformReviewService::class)->approve($record, Auth::user());

                        Notification::make()->title('Отзыв опубликован')->success()->send();
                    }),

                Action::make('reject')
                    ->label(fn (PlatformReview $r): string => $r->status === PlatformReview::STATUS_PUBLISHED ? 'Снять с витрины' : 'Не пропускать')
                    ->icon('heroicon-o-no-symbol')
                    ->color('danger')
                    ->visible(fn (PlatformReview $r): bool => self::canDecide() && $r->status !== PlatformReview::STATUS_HIDDEN)
                    ->modalHeading('Отклонить отзыв?')
                    // Критику площадки не снимают за то, что она критика:
                    // иначе витрина отзывов теряет смысл
                    ->modalDescription('Отзыв не будет виден на сайте. Автор получит вашу формулировку и сможет исправить текст. Отрицательная оценка сама по себе — не причина: снимают за контакты, брань, рекламу и отзывы не по делу.')
                    ->schema([
                        Textarea::make('note')
                            ->label('Формулировка решения')
                            ->required()
                            ->minLength(15)
                            ->rows(3)
                            ->helperText('Увидит автор отзыва. Например: «в тексте указан телефон — уберите его, и отзыв будет опубликован».'),
                    ])
                    ->action(function (PlatformReview $record, array $data): void {
                        app(PlatformReviewService::class)->reject($record, Auth::user(), $data['note']);

                        Notification::make()->title('Отзыв отклонён')->warning()->send();
                    }),

                Action::make('restore')
                    ->label('Вернуть на витрину')
                    ->icon('heroicon-o-arrow-uturn-left')
                    ->color('warning')
                    ->visible(fn (PlatformReview $r): bool => self::canDecide() && $r->status === PlatformReview::STATUS_HIDDEN)
                    ->requiresConfirmation()
                    ->modalHeading('Вернуть отзыв на витрину?')
                    ->action(function (PlatformReview $record): void {
                        app(PlatformReviewService::class)->restore($record, Auth::user());

                        Notification::make()->title('Отзыв снова виден')->success()->send();
                    }),
            ])
            ->emptyStateHeading('Новых отзывов нет')
            ->emptyStateDescription('Здесь появятся отзывы о площадке, которые ждут проверки. Снимите фильтр, чтобы увидеть все.');
    }

    public static function getPages(): array
    {
        return [
            'index' => ListPlatformReviews::route('/'),
        ];
    }
}
