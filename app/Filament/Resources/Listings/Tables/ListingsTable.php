<?php

declare(strict_types=1);

namespace App\Filament\Resources\Listings\Tables;

use App\Filament\Exports\ListingExporter;
use App\Models\Listing;
use App\Support\Notifier;
use Filament\Actions\Action;
use Filament\Actions\BulkActionGroup;
use Filament\Actions\DeleteBulkAction;
use Filament\Actions\ExportAction;
use Filament\Actions\Exports\Enums\ExportFormat;
use Filament\Forms\Components\Textarea;
use Filament\Notifications\Notification;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Table;
use Illuminate\Support\Facades\Auth;

/**
 * Объявления и очередь модерации.
 *
 * Отклонение требует причины: «отклонено» без объяснения человек
 * исправить не может и присылает то же самое повторно.
 */
class ListingsTable
{
    private const STATUS_LABELS = [
        Listing::STATUS_DRAFT => 'Черновик',
        Listing::STATUS_MODERATION => 'На проверке',
        Listing::STATUS_ACTIVE => 'Активно',
        Listing::STATUS_REJECTED => 'Отклонено',
        Listing::STATUS_EXPIRED => 'Истекло',
        Listing::STATUS_ARCHIVED => 'Снято',
    ];

    public static function configure(Table $table): Table
    {
        return $table
            ->modifyQueryUsing(fn ($query) => $query->with(['company', 'category.translations']))
            /*
             * Выгрузка и загрузка данных (§6.4 ТЗ). Файл готовится
             * в очереди: выгрузка десятков тысяч строк в запросе
             * упирается в таймаут, а заказчик видит только «ошибка».
             */
            ->headerActions([
                ExportAction::make()
                    ->label('Выгрузить')
                    ->exporter(ListingExporter::class)
                    ->formats([ExportFormat::Xlsx, ExportFormat::Csv])
                    ->visible(fn (): bool => Auth::user()?->isSuperadmin() ?? false),
            ])
            ->columns([
                TextColumn::make('title')
                    ->label('Объявление')
                    ->searchable()
                    ->wrap()
                    ->description(fn (Listing $record): string => $record->category?->name() ?? 'Без категории')
                    ->limit(60),

                TextColumn::make('company.name')
                    ->label('Компания')
                    ->searchable()
                    ->toggleable(),

                TextColumn::make('type')
                    ->label('Тип')
                    ->badge()
                    ->formatStateUsing(fn (string $state): string => $state === 'demand' ? 'Запрос' : 'Предложение')
                    ->color(fn (string $state): string => $state === 'demand' ? 'warning' : 'info'),

                TextColumn::make('status')
                    ->label('Статус')
                    ->badge()
                    ->formatStateUsing(fn (string $state): string => self::STATUS_LABELS[$state] ?? $state)
                    ->color(fn (string $state): string => match ($state) {
                        Listing::STATUS_ACTIVE => 'success',
                        Listing::STATUS_MODERATION => 'warning',
                        Listing::STATUS_REJECTED => 'danger',
                        default => 'gray',
                    }),

                TextColumn::make('views_count')->label('Просмотры')->numeric()->sortable()->toggleable(),
                TextColumn::make('unlocks_count')->label('Контакты')->numeric()->sortable()->toggleable(),

                TextColumn::make('expires_at')
                    ->label('До')
                    ->date('d.m.Y')
                    ->placeholder('—')
                    ->sortable(),
            ])
            ->defaultSort('created_at', 'desc')
            ->filters([
                SelectFilter::make('status')
                    ->label('Статус')
                    ->options(self::STATUS_LABELS),

                SelectFilter::make('type')
                    ->label('Тип')
                    ->options(['supply' => 'Предложение', 'demand' => 'Запрос']),
            ])
            ->recordActions([
                Action::make('approve')
                    ->label('Одобрить')
                    ->icon('heroicon-o-check-circle')
                    ->color('success')
                    ->visible(fn (Listing $record): bool => $record->status === Listing::STATUS_MODERATION)
                    ->requiresConfirmation()
                    ->action(function (Listing $record): void {
                        $record->forceFill([
                            'status' => Listing::STATUS_ACTIVE,
                            'moderation_note' => null,
                            'published_at' => $record->published_at ?? now(),
                            'expires_at' => $record->expires_at ?? now()->addDays(Listing::LIFETIME_DAYS),
                        ])->save();

                        app(Notifier::class)->company(
                            $record->company,
                            'moderation',
                            "Объявление «{$record->title}» опубликовано",
                            ['tone' => 'success', 'url' => '/cabinet/listings'],
                        );

                        Notification::make()->title('Объявление опубликовано')->success()->send();
                    }),

                Action::make('reject')
                    ->label('Отклонить')
                    ->icon('heroicon-o-x-circle')
                    ->color('danger')
                    ->visible(fn (Listing $record): bool => in_array(
                        $record->status,
                        [Listing::STATUS_MODERATION, Listing::STATUS_ACTIVE],
                        true,
                    ))
                    ->schema([
                        Textarea::make('reason')
                            ->label('Причина отказа')
                            ->required()
                            ->minLength(10)
                            ->rows(3)
                            // Причина уходит человеку дословно: он должен
                            // понять, что именно исправить
                            ->helperText('Текст увидит владелец объявления. Напишите, что конкретно исправить.'),
                    ])
                    ->action(function (Listing $record, array $data): void {
                        $record->forceFill([
                            'status' => Listing::STATUS_REJECTED,
                            'moderation_note' => $data['reason'],
                        ])->save();

                        app(Notifier::class)->company(
                            $record->company,
                            'moderation',
                            "Объявление «{$record->title}» отклонено",
                            [
                                'tone' => 'danger',
                                'body' => $data['reason'],
                                'url' => '/cabinet/listings?status=rejected',
                            ],
                        );

                        Notification::make()->title('Объявление отклонено')->warning()->send();
                    }),
            ])
            ->toolbarActions([
                BulkActionGroup::make([
                    DeleteBulkAction::make(),
                ]),
            ])
            ->emptyStateHeading('Объявлений нет')
            ->emptyStateDescription('Здесь появятся объявления, отправленные на проверку.');
    }
}
