<?php

declare(strict_types=1);

namespace App\Filament\Resources\Resumes\Tables;

use App\Models\Resume;
use App\Support\AdminAccess;
use App\Support\ResumeOptions;
use Filament\Actions\Action;
use Filament\Actions\DeleteAction;
use Filament\Forms\Components\Textarea;
use Filament\Notifications\Notification;
use Filament\Support\Icons\Heroicon;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\Filter;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Table;

/**
 * Список резюме для модерации.
 *
 * Снятие требует формулировки: её видит соискатель у себя в кабинете,
 * и «ваше резюме снято» без причины он прочитает как произвол.
 * Удаление оставлено только на крайний случай — снятое резюме можно
 * вернуть, удалённое человек напишет заново с нуля.
 */
class ResumesTable
{
    private const STATUSES = [
        Resume::STATUS_DRAFT => 'Черновик',
        Resume::STATUS_PUBLISHED => 'В разделе',
        Resume::STATUS_HIDDEN => 'Снято автором',
        Resume::STATUS_BLOCKED => 'Снято модерацией',
    ];

    public static function configure(Table $table): Table
    {
        return $table
            ->modifyQueryUsing(fn ($query) => $query->with(['user', 'city.translations']))
            ->columns([
                TextColumn::make('title')
                    ->label('Должность')
                    ->searchable()
                    ->wrap()
                    ->description(fn (Resume $r): string => $r->contact_name ?: ($r->user?->name ?? '—')),

                TextColumn::make('field')
                    ->label('Сфера')
                    ->badge()
                    ->formatStateUsing(fn (?string $state): string => $state === null
                        ? '—'
                        : (ResumeOptions::fields()[$state] ?? $state))
                    ->placeholder('—'),

                TextColumn::make('experience_months')
                    ->label('Опыт')
                    ->formatStateUsing(function (int $state): string {
                        $years = intdiv($state, 12);
                        $months = $state % 12;

                        return $state === 0 ? 'без опыта' : trim(($years > 0 ? $years.' г. ' : '').($months > 0 ? $months.' мес.' : ''));
                    })
                    ->sortable(),

                TextColumn::make('city.slug')
                    ->label('Город')
                    ->formatStateUsing(fn (Resume $r): string => $r->city?->name() ?? '—')
                    ->placeholder('—')
                    ->toggleable(),

                TextColumn::make('status')
                    ->label('Состояние')
                    ->badge()
                    ->formatStateUsing(fn (string $state): string => self::STATUSES[$state] ?? $state)
                    ->color(fn (string $state): string => match ($state) {
                        Resume::STATUS_PUBLISHED => 'success',
                        Resume::STATUS_BLOCKED => 'danger',
                        default => 'gray',
                    })
                    // Причина снятия — сразу под состоянием: искать её
                    // в карточке модератор не станет
                    ->description(fn (Resume $r): ?string => $r->moderation_note)
                    ->wrap(),

                TextColumn::make('views_count')->label('Просмотров')->sortable()->toggleable(),

                TextColumn::make('published_at')
                    ->label('Опубликовано')
                    ->date('d.m.Y')
                    ->placeholder('—')
                    ->sortable(),
            ])
            ->defaultSort('published_at', 'desc')
            ->filters([
                SelectFilter::make('status')->label('Состояние')->options(self::STATUSES),

                SelectFilter::make('field')->label('Сфера')->options(ResumeOptions::fields()),

                /*
                 * Свежие — то, ради чего сюда заходят без жалобы:
                 * резюме публикуются сразу, и беглый просмотр новых
                 * заменяет очередь на проверку.
                 */
                Filter::make('fresh')
                    ->label('Опубликованы за неделю')
                    ->query(fn ($query) => $query
                        ->where('status', Resume::STATUS_PUBLISHED)
                        ->where('published_at', '>=', now()->subWeek())),
            ])
            ->recordActions([
                Action::make('open')
                    ->label('Открыть')
                    ->icon(Heroicon::OutlinedArrowTopRightOnSquare)
                    ->url(fn (Resume $r): string => url('/resume/'.$r->slug))
                    ->openUrlInNewTab()
                    ->visible(fn (Resume $r): bool => $r->isPublished()),

                Action::make('block')
                    ->label('Снять')
                    ->icon(Heroicon::OutlinedEyeSlash)
                    ->color('danger')
                    ->visible(fn (Resume $r): bool => $r->status !== Resume::STATUS_BLOCKED
                        && AdminAccess::allows('resumes.moderate'))
                    ->schema([
                        Textarea::make('note')
                            ->label('Причина')
                            ->required()
                            ->minLength(10)
                            ->rows(3)
                            ->helperText('Текст видит соискатель в кабинете. Без причины снятие выглядит произволом.'),
                    ])
                    ->action(function (Resume $record, array $data): void {
                        $record->forceFill([
                            'status' => Resume::STATUS_BLOCKED,
                            'moderation_note' => $data['note'],
                        ])->save();

                        Notification::make()->title('Резюме снято с публикации')->success()->send();
                    }),

                Action::make('restore')
                    ->label('Вернуть')
                    ->icon(Heroicon::OutlinedEye)
                    ->color('success')
                    ->requiresConfirmation()
                    ->modalDescription('Резюме вернётся в раздел, заметка модерации снимется.')
                    ->visible(fn (Resume $r): bool => $r->status === Resume::STATUS_BLOCKED
                        && AdminAccess::allows('resumes.moderate'))
                    ->action(function (Resume $record): void {
                        $record->forceFill([
                            'status' => Resume::STATUS_PUBLISHED,
                            'published_at' => $record->published_at ?? now(),
                            'moderation_note' => null,
                        ])->save();

                        Notification::make()->title('Резюме вернулось в раздел')->success()->send();
                    }),

                // Удаление — крайняя мера: снятое возвращается,
                // удалённое человек пишет заново
                DeleteAction::make()
                    ->visible(fn (): bool => AdminAccess::allows('resumes.delete')),
            ]);
    }
}
