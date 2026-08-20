<?php

namespace App\Filament\Resources\Settings\Pages;

use App\Filament\Resources\Settings\SettingResource;
use Filament\Actions\DeleteAction;
use Filament\Resources\Pages\EditRecord;

class EditSetting extends EditRecord
{
    protected static string $resource = SettingResource::class;

    protected function getHeaderActions(): array
    {
        return [
            DeleteAction::make(),
        ];
    }

    /**
     * Картинка живёт в отдельном поле формы.
     *
     * У остальных типов значение — строка, у изображения — файл,
     * и один компонент FileUpload с именем value приводил строку
     * к null для всех прочих настроек: скрытый компонент всё равно
     * участвует в состоянии формы.
     */
    protected function mutateFormDataBeforeFill(array $data): array
    {
        if (($data['type'] ?? null) === 'image') {
            $path = (string) ($data['value'] ?? '');
            $data['value_image'] = $path === '' ? [] : [$path];
        }

        return $data;
    }

    protected function mutateFormDataBeforeSave(array $data): array
    {
        // Тип берётся из записи, а не из формы: поле «Тип значения»
        // при редактировании отключено, и в данные формы не попадает
        if ($this->record->type === 'image') {
            // FileUpload отдаёт состояние списком путей, даже когда
            // файл один: настройке нужен сам путь, а не массив
            $image = $data['value_image'] ?? '';
            $data['value'] = (string) (is_array($image) ? (reset($image) ?: '') : $image);
        }

        unset($data['value_image']);

        return $data;
    }
}
