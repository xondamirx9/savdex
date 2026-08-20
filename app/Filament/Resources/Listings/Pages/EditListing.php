<?php

namespace App\Filament\Resources\Listings\Pages;

use App\Filament\Resources\Listings\ListingResource;
use App\Models\ListingImage;
use Filament\Actions\DeleteAction;
use Filament\Actions\ForceDeleteAction;
use Filament\Actions\RestoreAction;
use Filament\Resources\Pages\EditRecord;
use Illuminate\Support\Facades\Storage;

class EditListing extends EditRecord
{
    protected static string $resource = ListingResource::class;

    /** @var list<string> Пути фотографий, оставшиеся в форме при сохранении. */
    private array $gallery = [];

    protected function getHeaderActions(): array
    {
        return [
            DeleteAction::make(),
            ForceDeleteAction::make(),
            RestoreAction::make(),
        ];
    }

    /**
     * Фотографии живут отдельной таблицей, а не полем объявления.
     *
     * Поле формы `gallery` — список путей: при открытии он собирается
     * из listing_images по порядку, при сохранении таблица приводится
     * к тому, что осталось в форме. Так работает и порядок: первая
     * фотография в ряду становится обложкой каталога.
     */
    protected function mutateFormDataBeforeFill(array $data): array
    {
        $data['gallery'] = $this->record->images()
            ->orderBy('sort')
            ->pluck('path')
            ->all();

        return $data;
    }

    protected function mutateFormDataBeforeSave(array $data): array
    {
        $this->gallery = array_values(array_filter((array) ($data['gallery'] ?? [])));

        unset($data['gallery']);

        return $data;
    }

    protected function afterSave(): void
    {
        $existing = $this->record->images()->get()->keyBy('path');

        // Снятые в форме фотографии удаляются вместе с файлами:
        // осиротевший файл на диске не показывается нигде и остаётся
        // занимать место до конца жизни площадки
        foreach ($existing as $path => $image) {
            if (! in_array($path, $this->gallery, true)) {
                $this->deleteFiles($image);
                $image->delete();
            }
        }

        foreach ($this->gallery as $sort => $path) {
            $image = $existing->get($path);

            if ($image === null) {
                $this->record->images()->create(['path' => $path, 'sort' => $sort]);

                continue;
            }

            $image->forceFill(['sort' => $sort])->save();
        }
    }

    private function deleteFiles(ListingImage $image): void
    {
        $disk = Storage::disk('public');

        $disk->delete(array_filter([$image->path, $image->thumb_path]));
    }
}
