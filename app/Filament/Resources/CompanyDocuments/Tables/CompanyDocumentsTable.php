<?php

declare(strict_types=1);

namespace App\Filament\Resources\CompanyDocuments\Tables;

use App\Models\CompanyDocument;
use App\Services\ModerationService;
use Filament\Actions\Action;
use Filament\Forms\Components\Textarea;
use Filament\Notifications\Notification;
use Filament\Tables\Columns\IconColumn;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\Filter;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Table;
use Illuminate\Support\Facades\Auth;

/**
 * Документы компаний на проверку.
 *
 * Компания загружает свидетельство о регистрации или лицензию и ждёт
 * решения — раньше не дожидалась: статус ставился в pending, и очереди,
 * где документ увидит модератор, не было. При этом непроверенный
 * документ не показывается на визитке, то есть загрузка не давала
 * компании ровно ничего.
 *
 * Материалы — презентации, прайсы — сюда не попадают: они не
 * подтверждают статус и публикуются сразу.
 */
class CompanyDocumentsTable
{
    public static function configure(Table $table): Table
    {
        return $table
            ->modifyQueryUsing(fn ($query) => $query
                ->whereIn('type', array_keys(CompanyDocument::VERIFICATION_TYPES))
                ->with(['company', 'moderator']))
            ->columns([
                TextColumn::make('company.name')
                    ->label('Компания')
                    ->searchable()
                    ->description(fn (CompanyDocument $d): string => 'уровень проверки: '.$d->company?->verification_level),

                TextColumn::make('title')
                    ->label('Документ')
                    ->searchable()
                    ->description(fn (CompanyDocument $d): string => $d->typeLabel()),

                TextColumn::make('file_size')
                    ->label('Размер')
                    ->formatStateUsing(fn (CompanyDocument $d): ?string => $d->sizeLabel()),

                TextColumn::make('valid_until')
                    ->label('Действует до')
                    ->date('d.m.Y')
                    ->placeholder('бессрочно')
                    // Просроченный документ ничего не подтверждает,
                    // и это должно быть видно до открытия файла
                    ->color(fn (CompanyDocument $d): string => $d->isExpired() ? 'danger' : 'gray'),

                TextColumn::make('moderation_status')
                    ->label('Проверка')
                    ->badge()
                    ->formatStateUsing(fn (string $state): string => match ($state) {
                        CompanyDocument::STATUS_APPROVED => 'Принят',
                        CompanyDocument::STATUS_REJECTED => 'Отклонён',
                        default => 'Ждёт',
                    })
                    ->color(fn (string $state): string => match ($state) {
                        CompanyDocument::STATUS_APPROVED => 'success',
                        CompanyDocument::STATUS_REJECTED => 'danger',
                        default => 'warning',
                    })
                    ->description(fn (CompanyDocument $d): ?string => $d->moderation_note),

                IconColumn::make('is_public')->label('На визитке')->boolean()->toggleable(),

                TextColumn::make('created_at')->label('Загружен')->date('d.m.Y')->sortable(),
            ])
            ->defaultSort('created_at', 'desc')
            ->filters([
                Filter::make('pending')
                    ->label('Ждут проверки')
                    ->default()
                    ->query(fn ($query) => $query->where('moderation_status', CompanyDocument::STATUS_PENDING)),

                SelectFilter::make('moderation_status')->label('Проверка')->options([
                    CompanyDocument::STATUS_PENDING => 'Ждёт',
                    CompanyDocument::STATUS_APPROVED => 'Принят',
                    CompanyDocument::STATUS_REJECTED => 'Отклонён',
                ]),

                SelectFilter::make('type')->label('Тип')->options(CompanyDocument::VERIFICATION_TYPES),
            ])
            ->recordActions([
                Action::make('open')
                    ->label('Открыть файл')
                    ->icon('heroicon-o-document-magnifying-glass')
                    ->color('gray')
                    // Решать, не открыв документ, нельзя — ссылка первая
                    ->url(fn (CompanyDocument $d): string => route('files.download', $d->id))
                    ->openUrlInNewTab(),

                Action::make('approve')
                    ->label('Принять')
                    ->icon('heroicon-o-check-circle')
                    ->color('success')
                    ->visible(fn (CompanyDocument $d): bool => $d->moderation_status !== CompanyDocument::STATUS_APPROVED)
                    ->requiresConfirmation()
                    ->modalHeading('Принять документ?')
                    ->modalDescription('Документ станет виден на визитке, если компания разрешила его показ. Уровень проверки компании при этом не меняется — бейдж «Проверена» выдаётся отдельно, по совокупности документов.')
                    ->action(function (CompanyDocument $record): void {
                        app(ModerationService::class)->approveDocument($record, Auth::user());

                        Notification::make()->title('Документ принят')->success()->send();
                    }),

                Action::make('reject')
                    ->label('Отклонить')
                    ->icon('heroicon-o-x-circle')
                    ->color('danger')
                    ->visible(fn (CompanyDocument $d): bool => $d->moderation_status !== CompanyDocument::STATUS_REJECTED)
                    ->schema([
                        Textarea::make('reason')
                            ->label('Причина отказа')
                            ->required()
                            ->minLength(15)
                            ->rows(3)
                            ->helperText('Текст увидит компания. Без причины она пришлёт тот же файл ещё раз.'),
                    ])
                    ->action(function (CompanyDocument $record, array $data): void {
                        app(ModerationService::class)->rejectDocument($record, Auth::user(), $data['reason']);

                        Notification::make()->title('Документ отклонён')->warning()->send();
                    }),
            ])
            ->emptyStateHeading('Документов на проверке нет')
            ->emptyStateDescription('Здесь появятся свидетельства, лицензии и сертификаты, загруженные компаниями. Снимите фильтр, чтобы увидеть уже проверенные.');
    }
}
