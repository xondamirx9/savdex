<?php

declare(strict_types=1);

namespace App\Filament\Resources\Companies\Tables;

use App\Filament\Exports\CompanyExporter;
use App\Filament\Imports\CompanyImporter;
use App\Models\Company;
use App\Support\CompanyEmblem;
use App\Support\ImageStore;
use App\Support\Notifier;
use Filament\Actions\Action;
use Filament\Actions\BulkAction;
use Filament\Actions\BulkActionGroup;
use Filament\Actions\DeleteBulkAction;
use Filament\Actions\ExportAction;
use Filament\Actions\Exports\Enums\ExportFormat;
use Filament\Actions\ImportAction;
use Filament\Forms\Components\FileUpload;
use Filament\Forms\Components\Select;
use Filament\Forms\Components\Textarea;
use Filament\Notifications\Notification;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Filters\TrashedFilter;
use Filament\Tables\Table;
use Illuminate\Database\Eloquent\Collection;
use Illuminate\Support\Facades\Auth;

/**
 * Компании: верификация и блокировка.
 *
 * Бейдж «Проверена» выдаёт только модератор и только руками — купить
 * его нельзя ни на одном тарифе. Это обещание вынесено на витрину,
 * поэтому автоматической выдачи здесь нет и не будет.
 */
class CompaniesTable
{
    private const LEVELS = [
        Company::VERIFICATION_NONE => 'Не проверена',
        Company::VERIFICATION_CONTACTS => 'Контакты подтверждены',
        Company::VERIFICATION_COMPANY => 'Проверена',
        Company::VERIFICATION_EXTENDED => 'Проверена+',
    ];

    public static function configure(Table $table): Table
    {
        return $table
            ->modifyQueryUsing(fn ($query) => $query->with(['city.translations', 'country']))
            /*
             * Выгрузка и загрузка данных (§6.4 ТЗ). Файл готовится
             * в очереди: выгрузка десятков тысяч строк в запросе
             * упирается в таймаут, а заказчик видит только «ошибка».
             */
            ->headerActions([
                ExportAction::make()
                    ->label('Выгрузить')
                    ->exporter(CompanyExporter::class)
                    ->formats([ExportFormat::Xlsx, ExportFormat::Csv])
                    ->visible(fn (): bool => Auth::user()?->isSuperadmin() ?? false),

                ImportAction::make()
                    ->label('Загрузить')
                    ->importer(CompanyImporter::class)
                    ->visible(fn (): bool => Auth::user()?->isSuperadmin() ?? false),
            ])
            ->columns([
                TextColumn::make('name')
                    ->label('Компания')
                    ->searchable()
                    ->description(fn (Company $record): string => $record->tin ? "ИНН {$record->tin}" : 'ИНН не указан')
                    ->wrap(),

                TextColumn::make('city_id')
                    ->label('Город')
                    ->state(fn (Company $record): string => $record->city?->name() ?? '—')
                    ->toggleable(),

                TextColumn::make('verification_level')
                    ->label('Верификация')
                    ->badge()
                    ->formatStateUsing(fn ($state): string => self::LEVELS[(int) $state] ?? (string) $state)
                    ->color(fn ($state): string => match ((int) $state) {
                        Company::VERIFICATION_EXTENDED => 'warning',
                        Company::VERIFICATION_COMPANY => 'success',
                        default => 'gray',
                    }),

                TextColumn::make('listings_count')
                    ->label('Объявлений')
                    ->counts('listings')
                    ->sortable(),

                TextColumn::make('rating')
                    ->label('Рейтинг')
                    ->numeric(1)
                    ->sortable()
                    ->placeholder('—'),

                TextColumn::make('status')
                    ->label('Статус')
                    ->badge()
                    ->formatStateUsing(fn (string $state): string => $state === 'active' ? 'Активна' : 'Заблокирована')
                    ->color(fn (string $state): string => $state === 'active' ? 'success' : 'danger'),

                TextColumn::make('created_at')
                    ->label('Регистрация')
                    ->date('d.m.Y')
                    ->sortable()
                    ->toggleable(isToggledHiddenByDefault: true),
            ])
            ->defaultSort('created_at', 'desc')
            ->filters([
                SelectFilter::make('verification_level')->label('Верификация')->options(self::LEVELS),
                SelectFilter::make('status')->label('Статус')->options([
                    'active' => 'Активна',
                    'blocked' => 'Заблокирована',
                ]),
                TrashedFilter::make(),
            ])
            ->recordActions([
                Action::make('verify')
                    ->label('Верификация')
                    ->icon('heroicon-o-shield-check')
                    ->color('success')
                    ->schema([
                        Select::make('level')
                            ->label('Уровень')
                            ->options(self::LEVELS)
                            ->required()
                            ->helperText('«Проверена» — сверены свидетельство и ИНН. «Проверена+» — ещё лицензии и адрес.'),
                    ])
                    ->action(function (Company $record, array $data): void {
                        $level = (int) $data['level'];

                        $record->forceFill([
                            'verification_level' => $level,
                            'verified_at' => $level > 0 ? now() : null,
                            'verified_by' => $level > 0 ? Auth::id() : null,
                        ])->save();

                        app(Notifier::class)->company(
                            $record,
                            'moderation',
                            $level > 0
                                ? 'Компания прошла проверку: '.self::LEVELS[$level]
                                : 'Уровень верификации снят',
                            ['tone' => $level > 0 ? 'success' : 'warning', 'url' => '/cabinet/company'],
                        );

                        Notification::make()->title('Уровень обновлён')->success()->send();
                    }),

                /*
                 * Эмблема вместо логотипа: настоящие знаки площадка
                 * использовать не может (авторское право), а плашка
                 * с инициалами в цвете региона — своя и единообразная.
                 */
                Action::make('emblem')
                    ->label('Эмблема')
                    ->icon('heroicon-o-swatch')
                    ->color('gray')
                    ->requiresConfirmation()
                    ->modalHeading('Сгенерировать эмблему?')
                    ->modalDescription(fn (Company $record): string => $record->logo_path !== null
                        ? 'У компании уже есть логотип — он будет заменён сгенерированной эмблемой.'
                        : 'Компания получит плашку с инициалами в цвете своего региона.')
                    ->action(function (Company $record): void {
                        CompanyEmblem::assign($record);

                        Notification::make()->title('Эмблема установлена')->success()->send();
                    }),

                /*
                 * Логотип из админки: перезалить смазанный или снять
                 * неуместный. Файл обрабатывает ImageStore — тот же
                 * путь, что при загрузке владельцем из кабинета.
                 */
                Action::make('logo')
                    ->label('Логотип')
                    ->icon('heroicon-o-identification')
                    ->color('gray')
                    ->schema([
                        FileUpload::make('logo')
                            ->label('Файл логотипа')
                            ->image()
                            ->storeFiles(false)
                            ->maxSize(ImageStore::MAX_SIZE_KB)
                            ->helperText('JPG, PNG или WebP до 8 МБ, лучше квадратный и не меньше 512px. Пустое поле — убрать логотип, вернутся инициалы.'),
                    ])
                    ->action(function (Company $record, array $data): void {
                        $store = app(ImageStore::class);
                        $file = $data['logo'] ?? null;

                        if ($file === null) {
                            $store->delete($record->logo_path);
                            $record->forceFill(['logo_path' => null])->save();

                            Notification::make()->title('Логотип снят — снова инициалы')->success()->send();

                            return;
                        }

                        try {
                            $path = $store->store($file, "companies/{$record->id}", ImageStore::LOGO);
                        } catch (\RuntimeException) {
                            Notification::make()->title('Файл не удалось прочитать как изображение')->danger()->send();

                            return;
                        }

                        $previous = $record->logo_path;
                        $record->forceFill(['logo_path' => $path])->save();
                        $store->delete($previous);

                        Notification::make()->title('Логотип обновлён')->success()->send();
                    }),

                /*
                 * Обложка шапки визитки. Файл обрабатывает ImageStore —
                 * тот же путь, что при загрузке владельцем из кабинета.
                 */
                Action::make('cover')
                    ->label('Обложка')
                    ->icon('heroicon-o-photo')
                    ->color('gray')
                    ->schema([
                        FileUpload::make('cover')
                            ->label('Фото обложки')
                            ->image()
                            ->storeFiles(false)
                            ->maxSize(ImageStore::MAX_SIZE_KB)
                            ->helperText('JPG, PNG или WebP до 8 МБ. Широкий кадр: полоса в шапке визитки. Пустое поле — вернуть фирменный градиент.'),
                    ])
                    ->action(function (Company $record, array $data): void {
                        $store = app(ImageStore::class);
                        $file = $data['cover'] ?? null;

                        if ($file === null) {
                            $store->delete($record->cover_path);
                            $record->forceFill(['cover_path' => null])->save();

                            Notification::make()->title('Обложка снята — снова градиент')->success()->send();

                            return;
                        }

                        try {
                            $path = $store->store($file, "companies/{$record->id}", ImageStore::COVER);
                        } catch (\RuntimeException) {
                            Notification::make()->title('Файл не удалось прочитать как изображение')->danger()->send();

                            return;
                        }

                        $previous = $record->cover_path;
                        $record->forceFill(['cover_path' => $path])->save();
                        $store->delete($previous);

                        Notification::make()->title('Обложка обновлена')->success()->send();
                    }),

                Action::make('block')
                    ->label(fn (Company $record): string => $record->status === 'active' ? 'Заблокировать' : 'Разблокировать')
                    ->icon('heroicon-o-no-symbol')
                    ->color('danger')
                    ->schema(fn (Company $record): array => $record->status === 'active' ? [
                        Textarea::make('reason')
                            ->label('Причина блокировки')
                            ->required()
                            ->minLength(10)
                            ->rows(3)
                            // Блокировка без причины не даёт компании понять,
                            // что исправить, и превращается в спор
                            ->helperText('Компания увидит эту причину в кабинете'),
                    ] : [])
                    ->requiresConfirmation(fn (Company $record): bool => $record->status !== 'active')
                    ->action(function (Company $record, array $data): void {
                        $blocking = $record->status === 'active';

                        $record->forceFill([
                            'status' => $blocking ? 'blocked' : 'active',
                            'blocked_reason' => $blocking ? ($data['reason'] ?? null) : null,
                            'blocked_at' => $blocking ? now() : null,
                        ])->save();

                        // Объявления заблокированной компании не должны
                        // оставаться в выдаче
                        if ($blocking) {
                            $record->listings()->where('status', 'active')->update(['status' => 'archived']);
                        }

                        Notification::make()
                            ->title($blocking ? 'Компания заблокирована' : 'Компания разблокирована')
                            ->success()
                            ->send();
                    }),
            ])
            ->toolbarActions([
                BulkAction::make('emblems')
                    ->label('Сгенерировать эмблемы')
                    ->icon('heroicon-o-swatch')
                    ->requiresConfirmation()
                    ->modalHeading('Сгенерировать эмблемы выбранным?')
                    ->modalDescription('Компании без логотипа получат плашку с инициалами в цвете региона. Уже загруженные логотипы не трогаются.')
                    ->deselectRecordsAfterCompletion()
                    ->action(function (Collection $records): void {
                        $done = 0;

                        foreach ($records as $company) {
                            // Настоящий логотип дороже сгенерированного:
                            // массовое действие занятые плашки обходит
                            if ($company->logo_path === null) {
                                CompanyEmblem::assign($company);
                                $done++;
                            }
                        }

                        Notification::make()
                            ->title("Эмблем установлено: {$done}")
                            ->body($done < $records->count() ? 'Пропущено с логотипом: '.($records->count() - $done) : null)
                            ->success()
                            ->send();
                    }),

                BulkActionGroup::make([
                    /*
                     * Ограничение суперадмином — прямо на действии:
                     * canDeleteAny ресурса массовые действия не прячет,
                     * и без visible() модератор мог удалять записи пачкой.
                     */
                    DeleteBulkAction::make()
                        ->visible(fn (): bool => Auth::user()?->isSuperadmin() ?? false),
                ]),
            ]);
    }
}
