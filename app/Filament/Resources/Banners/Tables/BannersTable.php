<?php

declare(strict_types=1);

namespace App\Filament\Resources\Banners\Tables;

use App\Models\Banner;
use App\Support\Business;
use Filament\Actions\BulkActionGroup;
use Filament\Actions\DeleteAction;
use Filament\Actions\DeleteBulkAction;
use Filament\Actions\EditAction;
use Filament\Support\Enums\FontWeight;
use Filament\Tables\Columns\ImageColumn;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Filters\TernaryFilter;
use Filament\Tables\Table;

class BannersTable
{
    public static function configure(Table $table): Table
    {
        return $table
            ->modifyQueryUsing(fn ($query) => $query->with('images'))
            ->columns([
                ImageColumn::make('image_path')
                    ->label('Баннер')
                    ->disk('public')
                    ->height(40),

                TextColumn::make('name')
                    ->label('Название')
                    ->weight(FontWeight::Medium)
                    ->description(fn (Banner $record): string => Banner::PLACEMENTS[$record->placement] ?? $record->placement)
                    ->searchable(),

                /*
                 * Обратный отсчёт — ради него таблица и нужна.
                 *
                 * «до 30 октября» не говорит, пора ли готовить
                 * следующую акцию, а «осталось 2 дня» говорит.
                 */
                TextColumn::make('countdown')
                    ->label('Осталось')
                    ->state(fn (Banner $record): string => $record->countdown())
                    ->badge()
                    ->color(fn (Banner $record): string => match (true) {
                        ! $record->isLive() => 'gray',
                        $record->ends_at === null => 'success',
                        $record->ends_at->diffInDays() <= 3 => 'warning',
                        default => 'success',
                    }),

                TextColumn::make('starts_at')
                    ->label('С')
                    ->state(fn (Banner $record): string => $record->starts_at !== null
                        ? Business::local($record->starts_at)->format('d.m.Y H:i')
                        : 'сразу')
                    ->sortable(),

                TextColumn::make('ends_at')
                    ->label('По')
                    ->state(fn (Banner $record): string => $record->ends_at !== null
                        ? Business::local($record->ends_at)->format('d.m.Y H:i')
                        : 'бессрочно')
                    ->sortable(),

                TextColumn::make('images_count')
                    ->label('Языков')
                    ->counts('images')
                    ->badge()
                    ->formatStateUsing(fn ($state): string => (int) $state === 0 ? 'одна на все' : "+{$state}")
                    ->color('gray'),

                TextColumn::make('sort')
                    ->label('Порядок')
                    ->sortable()
                    ->toggleable(isToggledHiddenByDefault: true),
            ])
            ->defaultSort('sort')
            ->filters([
                SelectFilter::make('placement')
                    ->label('Место')
                    ->options(Banner::PLACEMENTS),

                TernaryFilter::make('is_active')->label('Включён'),

                /*
                 * «Висит сейчас» — не то же, что «включён»: включённый
                 * может ждать своей даты или уже кончиться, и в списке
                 * из двадцати акций отличить одно от другого глазами
                 * невозможно.
                 */
                TernaryFilter::make('live')
                    ->label('Висит сейчас')
                    ->queries(
                        true: fn ($query) => $query->live(),
                        false: fn ($query) => $query->whereNot(fn ($q) => $q->live()),
                        blank: fn ($query) => $query,
                    ),
            ])
            ->recordActions([
                EditAction::make(),
                DeleteAction::make(),
            ])
            ->toolbarActions([
                BulkActionGroup::make([
                    DeleteBulkAction::make(),
                ]),
            ])
            ->emptyStateHeading('Баннеров пока нет')
            ->emptyStateDescription('Кнопка «Создать» наверху: картинка, срок и место — и акция на сайте без разработчика.');
    }
}
