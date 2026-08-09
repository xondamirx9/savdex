<?php

declare(strict_types=1);

namespace App\Filament\Pages;

use App\Models\ContactUnlock;
use App\Services\ModerationService;
use BackedEnum;
use Filament\Actions\Action;
use Filament\Forms\Components\Textarea;
use Filament\Notifications\Notification;
use Filament\Pages\Page;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Concerns\InteractsWithTable;
use Filament\Tables\Contracts\HasTable;
use Filament\Tables\Filters\Filter;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Table;
use Illuminate\Support\Facades\Auth;
use UnitEnum;

/**
 * Жалобы на раскрытые контакты.
 *
 * Покупатель платит кредит за контакт и получает обещание: «проверим
 * и вернём кредит, если контакт действительно нерабочий». Обещание
 * жило только в тексте — статус жалобы ставился в pending, и на этом
 * всё заканчивалось.
 *
 * Отдельная страница, а не ресурс: раскрытие контакта не редактируется
 * и не создаётся руками, у него есть ровно два решения — вернуть или
 * отказать. Ресурс с формой и кнопкой «Создать» вводил бы в заблуждение.
 */
class Complaints extends Page implements HasTable
{
    use InteractsWithTable;

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedExclamationTriangle;

    protected static ?string $navigationLabel = 'Жалобы на контакты';

    protected static string|UnitEnum|null $navigationGroup = 'Модерация';

    protected static ?int $navigationSort = 2;

    protected string $view = 'filament.pages.complaints';

    public function getTitle(): string
    {
        return 'Жалобы на контакты';
    }

    /** Счётчик в меню: нерассмотренная жалоба — это долг перед покупателем. */
    public static function getNavigationBadge(): ?string
    {
        $count = ContactUnlock::where('complaint_status', 'pending')->count();

        return $count > 0 ? (string) $count : null;
    }

    public static function getNavigationBadgeColor(): ?string
    {
        return 'danger';
    }

    private static function noteField(string $helper): Textarea
    {
        return Textarea::make('note')
            ->label('Формулировка решения')
            ->required()
            ->minLength(15)
            ->rows(3)
            ->helperText($helper);
    }

    public function table(Table $table): Table
    {
        return $table
            ->query(
                ContactUnlock::query()
                    ->whereNotNull('complaint_status')
                    ->with(['company', 'targetCompany', 'moderator']),
            )
            ->columns([
                TextColumn::make('company.name')
                    ->label('Жалуется')
                    ->searchable()
                    ->description(fn (ContactUnlock $u): string => 'на: '.($u->targetCompany?->name ?? 'компания удалена')),

                TextColumn::make('complaint_reason')
                    ->label('Суть жалобы')
                    ->wrap()
                    ->limit(160),

                TextColumn::make('credits_spent')
                    ->label('Списано')
                    // Ноль означает не «бесплатно», а «из месячного лимита
                    // тарифа»: возвращать в этом случае надо лимит, а не кредит
                    ->formatStateUsing(fn (int $state): string => $state > 0
                        ? "{$state} кред."
                        : 'из лимита тарифа'),

                TextColumn::make('complaint_status')
                    ->label('Решение')
                    ->badge()
                    ->formatStateUsing(fn (string $state): string => match ($state) {
                        'pending' => 'Ждёт',
                        'accepted' => 'Возвращено',
                        default => 'Отказано',
                    })
                    ->color(fn (string $state): string => match ($state) {
                        'pending' => 'warning',
                        'accepted' => 'success',
                        default => 'gray',
                    })
                    ->description(fn (ContactUnlock $u): ?string => $u->moderator?->name),

                TextColumn::make('complained_at')->label('Подана')->dateTime('d.m.Y H:i')->sortable(),
            ])
            ->defaultSort('complained_at', 'desc')
            ->filters([
                Filter::make('pending')
                    ->label('Ждут решения')
                    ->default()
                    ->query(fn ($query) => $query->where('complaint_status', 'pending')),

                SelectFilter::make('complaint_status')->label('Решение')->options([
                    'pending' => 'Ждёт',
                    'accepted' => 'Возвращено',
                    'declined' => 'Отказано',
                ]),
            ])
            ->recordActions([
                Action::make('accept')
                    ->label('Вернуть списанное')
                    ->icon('heroicon-o-arrow-uturn-left')
                    ->color('success')
                    ->visible(fn (ContactUnlock $u): bool => $u->complaint_status === 'pending')
                    ->modalHeading('Признать жалобу обоснованной?')
                    ->modalDescription('Кредит вернётся на счёт компании, а израсходованный контакт по тарифу — в месячный лимит. Сам контакт останется открытым: показанное обратно не забрать.')
                    ->schema([self::noteField('Компания увидит это как ответ на жалобу.')])
                    ->action(function (ContactUnlock $record, array $data): void {
                        app(ModerationService::class)->acceptComplaint($record, Auth::user(), $data['note']);

                        Notification::make()->title('Списанное возвращено')->success()->send();
                    }),

                Action::make('decline')
                    ->label('Отказать')
                    ->icon('heroicon-o-x-circle')
                    ->color('danger')
                    ->visible(fn (ContactUnlock $u): bool => $u->complaint_status === 'pending')
                    ->modalHeading('Отклонить жалобу?')
                    ->modalDescription('Возврата не будет. Компания получит объяснение.')
                    ->schema([self::noteField('Отказ без причины покупатель прочитает как «деньги забрали молча».')])
                    ->action(function (ContactUnlock $record, array $data): void {
                        app(ModerationService::class)->declineComplaint($record, Auth::user(), $data['note']);

                        Notification::make()->title('Жалоба отклонена')->success()->send();
                    }),
            ])
            ->emptyStateHeading('Жалоб нет')
            ->emptyStateDescription('Здесь появятся жалобы на нерабочие контакты. По каждой площадка обещала вернуть кредит — или объяснить отказ.');
    }
}
