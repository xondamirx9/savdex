<?php

declare(strict_types=1);

namespace App\Filament\Resources\Communications\Tables;

use App\Models\Crm\Communication;
use App\Support\AdminAccess;
use Filament\Actions\BulkActionGroup;
use Filament\Actions\DeleteAction;
use Filament\Actions\DeleteBulkAction;
use Filament\Actions\EditAction;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\Filter;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;
use Illuminate\Support\Facades\Auth;

class CommunicationsTable
{
    public static function configure(Table $table): Table
    {
        return $table
            ->modifyQueryUsing(fn (Builder $query): Builder => $query->with(['author', 'contact', 'subject']))
            ->defaultSort('happened_at', 'desc')
            ->columns([
                TextColumn::make('happened_at')
                    ->label('Когда')
                    ->dateTime('d.m.Y H:i')
                    ->sortable()
                    ->description(fn (Communication $r): string => $r->happened_at->diffForHumans()),

                TextColumn::make('type')
                    ->label('Что')
                    ->badge()
                    ->state(fn (Communication $r): string => $r->typeLabel())
                    ->color(fn (Communication $r): string => match ($r->type) {
                        'call' => 'success',
                        'meeting' => 'warning',
                        'email' => 'info',
                        default => 'gray',
                    }),

                TextColumn::make('summary')
                    ->label('О чём')
                    ->searchable()
                    ->wrap()
                    ->limit(80),

                TextColumn::make('contact.name')
                    ->label('С кем')
                    ->placeholder('—'),

                TextColumn::make('subject')
                    ->label('По чему')
                    ->state(fn (Communication $r): ?string => $r->subject?->title)
                    ->placeholder('—'),

                TextColumn::make('author.name')
                    ->label('Кто записал')
                    ->placeholder('—')
                    ->toggleable(),
            ])
            ->filters([
                SelectFilter::make('type')
                    ->label('Тип')
                    ->options(Communication::TYPES),

                Filter::make('mine')
                    ->label('Мои')
                    ->query(fn (Builder $query): Builder => $query->where('author_id', Auth::id())),

                Filter::make('week')
                    ->label('За неделю')
                    ->query(fn (Builder $query): Builder => $query->where('happened_at', '>=', now()->subWeek())),
            ])
            ->recordActions([
                EditAction::make(),
                DeleteAction::make(),
            ])
            ->toolbarActions([
                BulkActionGroup::make([
                    DeleteBulkAction::make()
                        ->visible(fn (): bool => AdminAccess::allows('communications.delete')),
                ]),
            ])
            ->emptyStateHeading('Записей нет')
            ->emptyStateDescription('Сюда записывают состоявшиеся разговоры: звонки, письма, встречи. Пока — руками.');
    }
}
