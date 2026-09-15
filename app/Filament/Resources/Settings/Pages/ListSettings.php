<?php

namespace App\Filament\Resources\Settings\Pages;

use App\Filament\Resources\Settings\SettingResource;
use App\Support\AdminAccess;
use App\Support\Appearance;
use Filament\Actions\Action;
use Filament\Actions\CreateAction;
use Filament\Forms\Components\FileUpload;
use Filament\Notifications\Notification;
use Filament\Resources\Pages\ListRecords;

class ListSettings extends ListRecords
{
    protected static string $resource = SettingResource::class;

    protected function getHeaderActions(): array
    {
        return [
            $this->logoAction(),
            CreateAction::make(),
        ];
    }

    /**
     * Загрузка логотипа отдельной кнопкой над списком.
     *
     * Строку «Логотип площадки» заводит миграция, и менять знак можно
     * прямо в ней. Но знак — не то же, что телефон поддержки: его ищут
     * глазами, а не поиском по ключу, и находить его среди трёх десятков
     * строк внизу списка неудобно. Кнопка ставит его на виду.
     *
     * Она же — страховка. Настройку может удалить администратор: так
     * уже случилось с фоном первого экрана, и «Оформление» пропало из
     * админки вместе со способом сменить картинку. Кнопка заводит строку
     * заново, поэтому площадка не остаётся без возможности сменить знак.
     */
    private function logoAction(): Action
    {
        return Action::make('logo')
            ->label('Логотип площадки')
            ->icon('heroicon-o-photo')
            ->color('gray')
            ->visible(fn (): bool => AdminAccess::allows('settings.'.AdminAccess::EDIT))
            ->modalHeading('Логотип площадки')
            ->modalDescription('Знак в шапке, в подвале, на вкладке браузера и в самой админке.')
            ->modalSubmitActionLabel('Сохранить')
            // Текущий знак виден в окне: иначе не понять, меняешь ты
            // его или ставишь впервые
            ->fillForm(fn (): array => ['logo' => ($path = Appearance::logoPath()) === '' ? [] : [$path]])
            ->schema([
                FileUpload::make('logo')
                    ->label('Файл логотипа')
                    ->image()
                    /*
                     * Вектор принимается наравне с растром: знак стоит
                     * на размерах от 16 до 360 px сразу, и PNG на
                     * фавиконе мылит. Кадрировать знак незачем, поэтому
                     * редактор изображений не включаем.
                     */
                    ->acceptedFileTypes(['image/svg+xml', 'image/png', 'image/webp', 'image/jpeg'])
                    // Диск указан явно: витрина строит адрес знака через
                    // публичный диск, а по умолчанию Filament кладёт файл
                    // туда, где его не отдаст веб-сервер
                    ->disk('public')
                    ->directory('appearance')
                    ->maxSize(8192)
                    ->helperText(Appearance::LOGO_HINT),
            ])
            ->action(function (array $data): void {
                // FileUpload отдаёт состояние списком путей, даже когда
                // файл один: настройке нужен сам путь, а не массив
                $image = $data['logo'] ?? '';
                $path = (string) (is_array($image) ? (reset($image) ?: '') : $image);

                Appearance::setLogo($path);

                Notification::make()
                    ->success()
                    ->title($path === '' ? 'Вернули знак по умолчанию' : 'Логотип обновлён')
                    ->send();
            });
    }
}
