<?php

declare(strict_types=1);

namespace App\Filament\Resources\Listings\RelationManagers;

use App\Models\Listing;
use App\Models\ListingImage;
use App\Support\ImageStore;
use Filament\Actions\Action;
use Filament\Forms\Components\FileUpload;
use Filament\Notifications\Notification;
use Filament\Resources\RelationManagers\RelationManager;
use Filament\Tables\Columns\ImageColumn;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Table;
use RuntimeException;

/**
 * Фотографии объявления — прямо в карточке админки.
 *
 * Модератор и администратор правят снимки любого объявления:
 * заменить неудачное фото, убрать постороннее, докинуть свои.
 * Обработка та же, что у загрузки владельцем, — через ImageStore
 * с пережатием и миниатюрой: фото из админки не должно отличаться
 * от загруженного через мастер ни весом, ни поведением.
 */
class ImagesRelationManager extends RelationManager
{
    protected static string $relationship = 'images';

    protected static ?string $title = 'Фотографии';

    public function table(Table $table): Table
    {
        return $table
            // Перетаскивание строк меняет порядок — первым идёт обложка
            ->reorderable('sort')
            ->defaultSort('sort')
            ->columns([
                ImageColumn::make('thumb_path')
                    ->label('Фото')
                    ->disk('public')
                    ->imageHeight(64),

                TextColumn::make('sort')->label('Порядок'),

                TextColumn::make('created_at')->label('Загружено')->dateTime('d.m.Y H:i'),
            ])
            ->headerActions([
                Action::make('upload')
                    ->label('Загрузить фото')
                    ->icon('heroicon-o-arrow-up-tray')
                    ->color('primary')
                    ->schema([
                        FileUpload::make('photos')
                            ->label('Фотографии')
                            ->image()
                            ->multiple()
                            // Файл не сохраняется Filament'ом: обработку
                            // делает ImageStore — как при загрузке владельцем
                            ->storeFiles(false)
                            ->maxSize(8192)
                            ->helperText('JPG, PNG или WebP до 8 МБ. Пережимаются и получают миниатюру автоматически'),
                    ])
                    ->action(function (array $data): void {
                        /** @var Listing $listing */
                        $listing = $this->getOwnerRecord();
                        $store = app(ImageStore::class);

                        $sort = (int) $listing->images()->max('sort') + 1;
                        $saved = 0;

                        foreach ((array) ($data['photos'] ?? []) as $file) {
                            try {
                                $paths = $store->storeWithThumb($file, "listings/{$listing->id}");
                            } catch (RuntimeException) {
                                continue; // не изображение — молча пропускаем, остальные грузим
                            }

                            $listing->images()->create([...$paths, 'sort' => $sort++]);
                            $saved++;
                        }

                        Notification::make()
                            ->title("Загружено фотографий: {$saved}")
                            ->{$saved > 0 ? 'success' : 'warning'}()
                            ->send();
                    }),
            ])
            ->recordActions([
                Action::make('cover')
                    ->label('Сделать обложкой')
                    ->icon('heroicon-o-star')
                    ->visible(fn (ListingImage $record): bool => $record->sort !== 0)
                    ->action(function (ListingImage $record): void {
                        // Как в кабинете: поднять и перенумеровать без дыр
                        $record->forceFill(['sort' => -1])->save();

                        foreach ($record->listing->images()->orderBy('sort')->get()->values() as $i => $image) {
                            if ($image->sort !== $i) {
                                $image->forceFill(['sort' => $i])->save();
                            }
                        }

                        Notification::make()->title('Обложка обновлена')->success()->send();
                    }),

                Action::make('remove')
                    ->label('Удалить')
                    ->icon('heroicon-o-trash')
                    ->color('danger')
                    ->requiresConfirmation()
                    ->modalHeading('Удалить фотографию?')
                    ->modalDescription('Файл будет удалён безвозвратно вместе с миниатюрой.')
                    ->action(function (ListingImage $record): void {
                        app(ImageStore::class)->delete($record->path, $record->thumb_path);
                        $record->delete();

                        Notification::make()->title('Фотография удалена')->success()->send();
                    }),
            ])
            ->emptyStateHeading('Фотографий нет')
            ->emptyStateDescription('Загрузите снимки — первая фотография станет обложкой в каталоге.');
    }
}
