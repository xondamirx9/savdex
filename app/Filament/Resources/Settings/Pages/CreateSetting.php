<?php

namespace App\Filament\Resources\Settings\Pages;

use App\Filament\Resources\Settings\SettingResource;
use Filament\Resources\Pages\CreateRecord;

class CreateSetting extends CreateRecord
{
    protected static string $resource = SettingResource::class;

    /** Картинка приходит из отдельного поля формы — см. EditSetting. */
    protected function mutateFormDataBeforeCreate(array $data): array
    {
        if (($data['type'] ?? null) === 'image') {
            // FileUpload отдаёт состояние списком путей, даже когда
            // файл один: настройке нужен сам путь, а не массив
            $image = $data['value_image'] ?? '';
            $data['value'] = (string) (is_array($image) ? (reset($image) ?: '') : $image);
        }

        unset($data['value_image']);

        return $data;
    }
}
