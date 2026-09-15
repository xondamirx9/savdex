<?php

declare(strict_types=1);

namespace App\Filament\Resources\Contacts\Tables;

use App\Models\Crm\Contact;
use App\Support\AdminAccess;
use Filament\Actions\BulkActionGroup;
use Filament\Actions\DeleteAction;
use Filament\Actions\DeleteBulkAction;
use Filament\Actions\EditAction;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\Filter;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Builder;

class ContactsTable
{
    public static function configure(Table $table): Table
    {
        return $table
            ->modifyQueryUsing(fn (Builder $query): Builder => $query->with('company')->withCount(['leads', 'deals']))
            ->defaultSort('name')
            ->columns([
                TextColumn::make('name')
                    ->label('Имя')
                    ->searchable()
                    ->sortable()
                    ->description(fn (Contact $r): ?string => $r->position),

                TextColumn::make('company.name')
                    ->label('Компания')
                    ->searchable()
                    ->placeholder('не указана'),

                TextColumn::make('phone')
                    ->label('Телефон')
                    ->copyable()
                    ->searchable()
                    ->placeholder('—'),

                TextColumn::make('email')
                    ->label('Почта')
                    ->copyable()
                    ->searchable()
                    ->placeholder('—'),

                TextColumn::make('leads_count')
                    ->label('Лидов')
                    ->badge()
                    ->color('gray'),

                TextColumn::make('deals_count')
                    ->label('Сделок')
                    ->badge()
                    ->color('gray'),
            ])
            ->filters([
                Filter::make('orphans')
                    ->label('Без компании')
                    ->query(fn (Builder $query): Builder => $query->whereNull('company_id')),
            ])
            ->recordActions([
                EditAction::make(),
                DeleteAction::make(),
            ])
            ->toolbarActions([
                BulkActionGroup::make([
                    DeleteBulkAction::make()
                        ->visible(fn (): bool => AdminAccess::allows('contacts.delete')),
                ]),
            ])
            ->emptyStateHeading('Контактов нет')
            ->emptyStateDescription('Контакт — это человек: снабженец, директор, бухгалтер. У одной компании их бывает несколько.');
    }
}
