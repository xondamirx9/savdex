<?php

declare(strict_types=1);

namespace App\Filament\Resources\CompanyTypes\Tables;

use App\Models\Company;
use App\Models\CompanyType;
use Filament\Actions\DeleteAction;
use Filament\Actions\EditAction;
use Filament\Notifications\Notification;
use Filament\Tables\Columns\IconColumn;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Table;

class CompanyTypesTable
{
    public static function configure(Table $table): Table
    {
        return $table
            ->modifyQueryUsing(fn ($query) => $query->with('translations'))
            ->columns([
                TextColumn::make('name')
                    ->label('Название')
                    ->state(fn (CompanyType $record): string => $record->name())
                    ->description(fn (CompanyType $record): string => $record->code),

                TextColumn::make('translations_count')
                    ->label('Переводов')
                    ->counts('translations')
                    ->badge()
                    ->color(fn ($state): string => (int) $state >= 5 ? 'success' : 'warning')
                    ->formatStateUsing(fn ($state): string => "{$state} из 5"),

                TextColumn::make('companies')
                    ->label('Компаний')
                    ->state(fn (CompanyType $record): int => Company::where('type', $record->code)->count()),

                TextColumn::make('sort')->label('Порядок')->sortable(),

                IconColumn::make('is_active')->label('Доступен')->boolean(),
            ])
            ->defaultSort('sort')
            ->reorderable('sort')
            ->paginated(false)
            ->recordActions([
                EditAction::make(),

                DeleteAction::make()
                    /*
                     * Тип с компаниями удалять нельзя: у них останется
                     * ссылка на несуществующее значение, и в карточке
                     * вместо типа появится сырой код.
                     */
                    ->before(function (CompanyType $record, DeleteAction $action): void {
                        $count = Company::where('type', $record->code)->count();

                        if ($count > 0) {
                            Notification::make()
                                ->title("Тип используют {$count} компаний")
                                ->body('Выключите его вместо удаления — тогда он исчезнет из выбора, но останется у тех, кто уже выбрал.')
                                ->danger()
                                ->send();

                            $action->cancel();
                        }
                    }),
            ])
            ->emptyStateHeading('Типов нет')
            ->emptyStateDescription('Пока справочник пуст, в форме регистрации показывается встроенный список.');
    }
}
