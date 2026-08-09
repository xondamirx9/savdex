<?php

declare(strict_types=1);

namespace App\Filament\Resources\Reviews\Tables;

use App\Models\Review;
use App\Services\ModerationService;
use Filament\Actions\Action;
use Filament\Forms\Components\Textarea;
use Filament\Notifications\Notification;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\Filter;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Table;
use Illuminate\Support\Facades\Auth;

/**
 * Отзывы и споры по ним.
 *
 * Компания может оспорить отзыв, который считает недостоверным.
 * Раньше оспаривание заканчивалось статусом «pending» и тишиной:
 * заявление уходило в базу, а экрана, где его увидит модератор,
 * не существовало.
 *
 * Удаления нет намеренно: скрытый отзыв возвращается на витрину,
 * удалённый — нет. Возможность стирать неудобные отзывы обесценивает
 * рейтинг целиком.
 */
class ReviewsTable
{
    private const DISPUTES = [
        'pending' => 'На рассмотрении',
        'accepted' => 'Удовлетворён',
        'declined' => 'Отклонён',
    ];

    /** Формулировка решения уходит обеим сторонам дословно. */
    private static function noteField(string $helper): Textarea
    {
        return Textarea::make('note')
            ->label('Формулировка решения')
            ->required()
            ->minLength(15)
            ->rows(3)
            ->helperText($helper);
    }

    public static function configure(Table $table): Table
    {
        return $table
            ->modifyQueryUsing(fn ($query) => $query->with(['company', 'authorCompany', 'moderator']))
            ->columns([
                TextColumn::make('company.name')
                    ->label('О компании')
                    ->searchable()
                    ->description(fn (Review $r): string => 'автор: '.($r->authorCompany?->name ?? 'удалён')),

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

                TextColumn::make('body')
                    ->label('Отзыв')
                    ->wrap()
                    ->limit(120)
                    ->searchable(),

                TextColumn::make('status')
                    ->label('На витрине')
                    ->badge()
                    ->formatStateUsing(fn (string $state): string => match ($state) {
                        Review::STATUS_PUBLISHED => 'Виден',
                        Review::STATUS_MODERATION => 'Ждёт проверки',
                        default => 'Скрыт',
                    })
                    ->color(fn (string $state): string => match ($state) {
                        Review::STATUS_PUBLISHED => 'success',
                        Review::STATUS_MODERATION => 'warning',
                        default => 'gray',
                    })
                    // Что насторожило автоматическую проверку — сразу
                    // под статусом, чтобы не искать это в тексте
                    ->description(fn (Review $r): ?string => $r->screening_flags)
                    ->wrap(),

                TextColumn::make('dispute_status')
                    ->label('Спор')
                    ->badge()
                    ->formatStateUsing(fn (?string $state): string => self::DISPUTES[$state] ?? '—')
                    ->color(fn (?string $state): string => match ($state) {
                        'pending' => 'warning',
                        'accepted' => 'success',
                        default => 'gray',
                    })
                    ->description(fn (Review $r): ?string => $r->dispute_reason)
                    ->wrap()
                    ->placeholder('—'),

                TextColumn::make('created_at')->label('Оставлен')->date('d.m.Y')->sortable(),

                TextColumn::make('moderated_at')
                    ->label('Решение')
                    ->date('d.m.Y')
                    ->description(fn (Review $r): ?string => $r->moderator?->name)
                    ->placeholder('—')
                    ->toggleable(isToggledHiddenByDefault: true),
            ])
            ->defaultSort('created_at', 'desc')
            ->filters([
                /*
                 * Всё, что ждёт решения: новые отзывы на премодерации
                 * и споры по опубликованным. Одним фильтром, а не двумя
                 * вкладками: это одна очередь работы, и разделять её
                 * значит заставлять модератора помнить про вторую.
                 */
                Filter::make('needs_action')
                    ->label('Ждут решения')
                    ->default()
                    ->query(fn ($query) => $query->where(fn ($q) => $q
                        ->where('status', Review::STATUS_MODERATION)
                        ->orWhere('dispute_status', 'pending'))),

                Filter::make('flagged')
                    ->label('С отметками проверки')
                    ->query(fn ($query) => $query->whereNotNull('screening_flags')),

                SelectFilter::make('status')->label('На витрине')->options([
                    Review::STATUS_PUBLISHED => 'Виден',
                    Review::STATUS_MODERATION => 'Ждёт проверки',
                    Review::STATUS_HIDDEN => 'Скрыт',
                ]),

                SelectFilter::make('rating')->label('Оценка')->options([
                    5 => '5', 4 => '4', 3 => '3', 2 => '2', 1 => '1',
                ]),
            ])
            ->recordActions([
                Action::make('approve')
                    ->label('Опубликовать')
                    ->icon('heroicon-o-check-badge')
                    ->color('success')
                    ->visible(fn (Review $r): bool => $r->status === Review::STATUS_MODERATION)
                    ->requiresConfirmation()
                    ->modalHeading('Опубликовать отзыв?')
                    ->modalDescription('Отзыв появится на странице компании и войдёт в рейтинг. Компания получит уведомление и сможет ответить.')
                    ->action(function (Review $record): void {
                        app(ModerationService::class)->approveReview($record, Auth::user());

                        Notification::make()->title('Отзыв опубликован')->success()->send();
                    }),

                Action::make('rejectReview')
                    ->label('Не пропускать')
                    ->icon('heroicon-o-no-symbol')
                    ->color('danger')
                    ->visible(fn (Review $r): bool => $r->status === Review::STATUS_MODERATION)
                    ->modalHeading('Отклонить отзыв?')
                    ->modalDescription('Отзыв не появится на витрине. Автор получит вашу формулировку — без неё он решит, что площадка убирает неудобное.')
                    ->schema([
                        self::noteField('Увидит автор отзыва. Например: «в тексте указан телефон — контакты на площадке раскрываются платно».'),
                    ])
                    ->action(function (Review $record, array $data): void {
                        app(ModerationService::class)->rejectReview($record, Auth::user(), $data['note']);

                        Notification::make()->title('Отзыв отклонён')->warning()->send();
                    }),

                Action::make('acceptDispute')
                    ->label('Скрыть отзыв')
                    ->icon('heroicon-o-eye-slash')
                    ->color('danger')
                    ->visible(fn (Review $r): bool => $r->dispute_status === 'pending')
                    ->modalHeading('Удовлетворить спор?')
                    ->modalDescription('Отзыв исчезнет с витрины, рейтинг компании пересчитается. Автор отзыва получит уведомление с вашей формулировкой.')
                    ->schema([
                        self::noteField('Увидят обе стороны: и компания, и автор отзыва. Напишите, что именно не подтвердилось.'),
                    ])
                    ->action(function (Review $record, array $data): void {
                        app(ModerationService::class)->acceptDispute($record, Auth::user(), $data['note']);

                        Notification::make()->title('Отзыв скрыт, рейтинг пересчитан')->success()->send();
                    }),

                Action::make('declineDispute')
                    ->label('Оставить отзыв')
                    ->icon('heroicon-o-check-circle')
                    ->color('success')
                    ->visible(fn (Review $r): bool => $r->dispute_status === 'pending')
                    ->modalHeading('Отклонить спор?')
                    ->modalDescription('Отзыв останется на витрине. Компания получит объяснение.')
                    ->schema([
                        self::noteField('Компания прочитает это как ответ на своё обращение.'),
                    ])
                    ->action(function (Review $record, array $data): void {
                        app(ModerationService::class)->declineDispute($record, Auth::user(), $data['note']);

                        Notification::make()->title('Спор отклонён')->success()->send();
                    }),

                Action::make('restore')
                    ->label('Вернуть на витрину')
                    ->icon('heroicon-o-arrow-uturn-left')
                    ->color('warning')
                    // Решение бывает ошибочным, и откат должен быть
                    // таким же простым действием, как и само решение
                    ->visible(fn (Review $r): bool => $r->status === 'hidden')
                    ->requiresConfirmation()
                    ->modalHeading('Вернуть отзыв на витрину?')
                    ->action(function (Review $record): void {
                        app(ModerationService::class)->restoreReview($record, Auth::user());

                        Notification::make()->title('Отзыв снова виден')->success()->send();
                    }),
            ])
            ->emptyStateHeading('Споров нет')
            ->emptyStateDescription('Здесь появятся отзывы, которые компании считают недостоверными. Снимите фильтр, чтобы увидеть все отзывы.');
    }
}
