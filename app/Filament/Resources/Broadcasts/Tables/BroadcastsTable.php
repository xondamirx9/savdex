<?php

declare(strict_types=1);

namespace App\Filament\Resources\Broadcasts\Tables;

use App\Filament\Resources\Broadcasts\Schemas\BroadcastForm;
use App\Models\Broadcast;
use App\Support\Notifier;
use Filament\Actions\Action;
use Filament\Actions\BulkActionGroup;
use Filament\Actions\DeleteAction;
use Filament\Actions\DeleteBulkAction;
use Filament\Actions\EditAction;
use Filament\Notifications\Notification;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Table;
use Illuminate\Support\Facades\Auth;

class BroadcastsTable
{
    public static function configure(Table $table): Table
    {
        return $table
            ->columns([
                TextColumn::make('title')
                    ->label('Заголовок')
                    ->searchable()
                    ->description(fn (Broadcast $record): string => str($record->body)->limit(80)->toString())
                    ->wrap(),

                TextColumn::make('audience')
                    ->label('Кому')
                    ->state(fn (Broadcast $record): string => $record->audienceLabel())
                    ->badge(),

                TextColumn::make('recipients_count')
                    ->label('Получили')
                    ->numeric()
                    ->sortable(),

                TextColumn::make('sent_at')
                    ->label('Отправлена')
                    ->dateTime('d.m.Y H:i')
                    ->placeholder('черновик')
                    ->sortable(),

                TextColumn::make('sender.name')
                    ->label('Автор')
                    ->placeholder('—')
                    ->toggleable(),
            ])
            ->defaultSort('created_at', 'desc')
            ->recordActions([
                /*
                 * Отправка отдельным действием со вторым подтверждением
                 * и точным числом получателей: уведомление уходит тысячам
                 * людей, и отозвать его нельзя.
                 */
                Action::make('send')
                    ->label('Отправить')
                    ->icon('heroicon-o-paper-airplane')
                    ->color('primary')
                    ->visible(fn (Broadcast $record): bool => $record->sent_at === null)
                    ->requiresConfirmation()
                    ->modalHeading('Отправить рассылку?')
                    ->modalDescription(fn (Broadcast $record): string => sprintf(
                        'Получат %d человек. Отменить отправку и отозвать уведомления будет нельзя.',
                        BroadcastForm::countRecipients($record->audience, $record->audience_value),
                    ))
                    ->modalSubmitActionLabel('Отправить')
                    ->action(function (Broadcast $record): void {
                        $record->forceFill(['sent_by' => Auth::id()])->save();

                        $sent = app(Notifier::class)->broadcast($record);

                        Notification::make()
                            ->title("Рассылка отправлена: {$sent} получателей")
                            ->success()
                            ->send();
                    }),

                EditAction::make()
                    // Отправленную рассылку править бессмысленно: уведомления
                    // уже созданы и живут своей жизнью
                    ->visible(fn (Broadcast $record): bool => $record->sent_at === null),

                DeleteAction::make(),
            ])
            ->toolbarActions([
                BulkActionGroup::make([
                    DeleteBulkAction::make(),
                ]),
            ])
            ->emptyStateHeading('Рассылок пока не было')
            ->emptyStateDescription('Рассылка появится у пользователей в колокольчике и в разделе «Уведомления».');
    }
}
