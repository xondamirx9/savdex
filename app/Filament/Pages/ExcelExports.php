<?php

declare(strict_types=1);

namespace App\Filament\Pages;

use App\Models\User;
use App\Support\AdminAccess;
use App\Support\AdminLog;
use App\Support\Business;
use App\Support\DatabaseExports;
use BackedEnum;
use Filament\Actions\Action;
use Filament\Notifications\Notification;
use Filament\Pages\Page;
use Filament\Support\Icons\Heroicon;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Auth;
use UnitEnum;

/**
 * Выгрузка базы в Excel — кнопкой, а не командой в Shell.
 *
 * Выгрузку делают регулярно. Раньше её можно было запустить только
 * в Shell на Render, файлы ложились не на постоянный диск и пропадали
 * при следующем деплое, а скачать их из Shell было нельзя. Здесь кнопка
 * ставит выгрузку в очередь, а список показывает ход, файлы и итог
 * сверки PHP- и Python-версий (см. config/exports.php).
 */
class ExcelExports extends Page
{
    public static function canAccess(): bool
    {
        return AdminAccess::allows('backups.view');
    }

    protected static string|BackedEnum|null $navigationIcon = Heroicon::OutlinedArrowDownTray;

    protected static ?string $navigationLabel = 'Выгрузка в Excel';

    protected static string|UnitEnum|null $navigationGroup = 'Система';

    protected static ?int $navigationSort = 90;

    protected static ?string $slug = 'excel-exports';

    protected string $view = 'filament.pages.excel-exports';

    public function getTitle(): string
    {
        return 'Выгрузка в Excel';
    }

    public function getSubheading(): ?string
    {
        return 'Вся база в двух книгах: компании и объявления. Файлы хранятся на постоянном диске, деплой их не стирает.';
    }

    protected function getHeaderActions(): array
    {
        return [
            Action::make('run')
                ->label('Выгрузить сейчас')
                ->icon(Heroicon::OutlinedArrowDownTray)
                ->visible(fn (): bool => AdminAccess::allows('backups.export'))
                // Вторая выгрузка поверх идущей удвоила бы нагрузку на базу
                // ради того же файла
                ->disabled(fn (): bool => app(DatabaseExports::class)->active() !== null)
                ->requiresConfirmation()
                ->modalHeading('Выгрузить базу в Excel?')
                ->modalDescription('В файлах будут почта, телефоны и IP-адреса всех пользователей площадки. Храните их так же бережно, как саму базу. Выгрузка займёт до пары минут; запуск и каждое скачивание записываются в журнал действий.')
                ->modalSubmitActionLabel('Выгрузить')
                ->action(function (): void {
                    $user = Auth::user();
                    $id = app(DatabaseExports::class)->queue($user instanceof User ? $user : null);

                    if ($id === null) {
                        Notification::make()->title('Выгрузка уже идёт — дождитесь её')->warning()->send();

                        return;
                    }

                    AdminLog::record('exported', 'backups', note: "Выгрузка базы в Excel: {$id}");

                    Notification::make()
                        ->title('Выгрузка запущена')
                        ->body('Страница обновится сама, когда файлы будут готовы.')
                        ->success()
                        ->send();
                }),
        ];
    }

    /** @return array<string, mixed> */
    protected function getViewData(): array
    {
        $exports = app(DatabaseExports::class);

        return [
            'runs' => $exports->all(),
            'active' => $exports->active() !== null,
            'canDownload' => AdminAccess::allows('backups.export'),
            'keep' => (int) config('exports.keep', 10),
            'primary' => $exports->primary(),
        ];
    }

    /** Время по Ташкенту: администратор смотрит на свои часы. */
    public static function when(?string $iso): string
    {
        return $iso === null ? '—' : Business::local(Carbon::parse($iso))->format('d.m.Y H:i');
    }
}
