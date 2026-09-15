<?php

declare(strict_types=1);

namespace App\Filament\Resources\Listings\Tables;

use App\Filament\Exports\ListingExporter;
use App\Models\Listing;
use App\Services\ListingWorkbookImport;
use App\Support\AdminAccess;
use App\Support\AdminLog;
use App\Support\ListingWorkbookTemplate;
use App\Support\Notifier;
use Filament\Actions\Action;
use Filament\Actions\BulkActionGroup;
use Filament\Actions\DeleteBulkAction;
use Filament\Actions\ExportAction;
use Filament\Actions\Exports\Enums\ExportFormat;
use Filament\Forms\Components\FileUpload;
use Filament\Forms\Components\Textarea;
use Filament\Forms\Components\Toggle;
use Filament\Notifications\Notification;
use Filament\Tables\Columns\TextColumn;
use Filament\Tables\Filters\SelectFilter;
use Filament\Tables\Table;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Auth;
use Illuminate\Support\HtmlString;

/**
 * Объявления и очередь модерации.
 *
 * Отклонение требует причины: «отклонено» без объяснения человек
 * исправить не может и присылает то же самое повторно.
 */
class ListingsTable
{
    private const STATUS_LABELS = [
        Listing::STATUS_DRAFT => 'Черновик',
        Listing::STATUS_MODERATION => 'На проверке',
        Listing::STATUS_ACTIVE => 'Активно',
        Listing::STATUS_REJECTED => 'Отклонено',
        Listing::STATUS_EXPIRED => 'Истекло',
        Listing::STATUS_ARCHIVED => 'Снято',
    ];

    public static function configure(Table $table): Table
    {
        return $table
            /*
             * Пустые черновики скрыты: их создаёт сам мастер объявления
             * при каждом заходе на «Создать» и переиспользует при
             * следующем. Удалять их из админки бессмысленно — кабинет
             * пользователя тут же заведёт новый, и список «не чистится».
             */
            ->modifyQueryUsing(fn ($query) => $query
                ->with(['company', 'category.translations'])
                ->whereNot(fn ($q) => $q
                    ->where('status', Listing::STATUS_DRAFT)
                    ->where('title', '')))
            /*
             * Выгрузка и загрузка данных (§6.4 ТЗ). Файл готовится
             * в очереди: выгрузка десятков тысяч строк в запросе
             * упирается в таймаут, а заказчик видит только «ошибка».
             */
            ->headerActions([
                ExportAction::make()
                    // Выгрузка уносит персональные данные целым файлом,
                    // загрузка создаёт записи пачкой мимо форм — оба следа нужны
                    ->before(function (): void {
                        AdminLog::record('exported', 'listings');
                    })
                    ->label('Выгрузить')
                    ->exporter(ListingExporter::class)
                    ->formats([ExportFormat::Xlsx, ExportFormat::Csv])
                    ->visible(fn (): bool => AdminAccess::allows('listings.export')),

                /*
                 * Загрузка каталога книгой Excel — вместе с фотографиями.
                 *
                 * Обычный импорт Filament принимает только CSV, а в CSV
                 * картинку не положишь: заказчик собирает каталог в Excel
                 * и вставляет снимки прямо в строку товара. Разбирает
                 * книгу ListingWorkbookImport, здесь только окно и отчёт.
                 */
                Action::make('importWorkbook')
                    ->label('Загрузить')
                    ->icon('heroicon-o-arrow-up-tray')
                    ->color('gray')
                    ->modalHeading('Загрузка товаров из Excel')
                    ->modalSubmitActionLabel('Загрузить')
                    ->schema([
                        FileUpload::make('workbook')
                            ->label('Книга Excel')
                            ->storeFiles(false)
                            ->required()
                            ->acceptedFileTypes(['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'])
                            // Фотографии лежат внутри книги, поэтому файл
                            // тяжелее обычной таблицы на порядок
                            ->maxSize(51200)
                            ->helperText(new HtmlString(
                                'Формат XLSX. Первая строка — названия столбцов, дальше по строке на товар.<br>'
                                .'Фотографии вставьте прямо в лист, в строку своего товара: сколько снимков '
                                .'в строке, столько и попадёт в объявление (до '.Listing::MAX_IMAGES.'). '
                                .'Формат снимков любой, какой открывает Excel.<br>'
                                .'Строка с «Номером» правит объявление с этим номером, без номера — ищется '
                                .'по названию и компании, не нашлось — заводится новое.'
                            )),

                        Toggle::make('replace')
                            ->label('Заменить фотографии, если они уже есть')
                            ->helperText('Обычно снимки добавляются только объявлениям без фотографий — '
                                .'повторная загрузка того же файла не плодит одинаковые.'),
                    ])
                    ->extraModalFooterActions([
                        Action::make('workbookTemplate')
                            ->label('Скачать образец')
                            ->color('gray')
                            ->link()
                            ->action(fn () => response()->streamDownload(function (): void {
                                $path = tempnam(sys_get_temp_dir(), 'savdex-template');
                                ListingWorkbookTemplate::write($path);

                                echo (string) file_get_contents($path);

                                @unlink($path);
                            }, 'savdex-tovary-obrazec.xlsx')),
                    ])
                    ->action(function (array $data): void {
                        $file = $data['workbook'] ?? null;

                        if (! $file instanceof UploadedFile) {
                            Notification::make()->title('Файл не получен')->danger()->send();

                            return;
                        }

                        // Книга копируется в обычный файл: ZipArchive не
                        // умеет читать потоки, а временный диск Livewire
                        // не обязан быть локальным
                        $copy = (string) tempnam(sys_get_temp_dir(), 'savdex-workbook');
                        file_put_contents($copy, $file->get());

                        try {
                            $result = app(ListingWorkbookImport::class)
                                ->run($copy, Auth::user(), (bool) ($data['replace'] ?? false));
                        } finally {
                            @unlink($copy);
                        }

                        // След в журнале: загрузка создаёт записи пачкой,
                        // минуя формы и их проверки
                        AdminLog::record('imported', 'listings', note: 'Создано: '.$result['created']
                            .', обновлено: '.$result['updated']
                            .', фотографий: '.$result['photos']);

                        self::report($result);
                    })
                    ->visible(fn (): bool => AdminAccess::allows('listings.import')),
            ])
            ->columns([
                TextColumn::make('title')
                    ->label('Объявление')
                    ->searchable()
                    ->wrap()
                    ->description(fn (Listing $record): string => $record->category?->name() ?? 'Без категории')
                    ->limit(60),

                TextColumn::make('company.name')
                    ->label('Компания')
                    ->searchable()
                    ->toggleable(),

                TextColumn::make('type')
                    ->label('Тип')
                    ->badge()
                    ->formatStateUsing(fn (string $state): string => $state === 'demand' ? 'Запрос' : 'Предложение')
                    ->color(fn (string $state): string => $state === 'demand' ? 'warning' : 'info'),

                TextColumn::make('status')
                    ->label('Статус')
                    ->badge()
                    ->formatStateUsing(fn (string $state): string => self::STATUS_LABELS[$state] ?? $state)
                    ->color(fn (string $state): string => match ($state) {
                        Listing::STATUS_ACTIVE => 'success',
                        Listing::STATUS_MODERATION => 'warning',
                        Listing::STATUS_REJECTED => 'danger',
                        default => 'gray',
                    }),

                TextColumn::make('views_count')->label('Просмотры')->numeric()->sortable()->toggleable(),
                TextColumn::make('unlocks_count')->label('Контакты')->numeric()->sortable()->toggleable(),

                TextColumn::make('expires_at')
                    ->label('До')
                    ->date('d.m.Y')
                    ->placeholder('—')
                    ->sortable(),
            ])
            ->defaultSort('created_at', 'desc')
            ->filters([
                SelectFilter::make('status')
                    ->label('Статус')
                    ->options(self::STATUS_LABELS),

                SelectFilter::make('type')
                    ->label('Тип')
                    ->options(['supply' => 'Предложение', 'demand' => 'Запрос']),
            ])
            ->recordActions([
                Action::make('approve')
                    ->label('Одобрить')
                    ->icon('heroicon-o-check-circle')
                    ->color('success')
                    ->visible(fn (Listing $record): bool => $record->status === Listing::STATUS_MODERATION)
                    ->requiresConfirmation()
                    ->action(function (Listing $record): void {
                        $record->forceFill([
                            'status' => Listing::STATUS_ACTIVE,
                            'moderation_note' => null,
                            'published_at' => $record->published_at ?? now(),
                            'expires_at' => $record->expires_at ?? now()->addDays(Listing::LIFETIME_DAYS),
                        ])->save();

                        app(Notifier::class)->company(
                            $record->company,
                            'moderation',
                            "Объявление «{$record->title}» опубликовано",
                            ['tone' => 'success', 'url' => '/cabinet/listings'],
                        );

                        Notification::make()->title('Объявление опубликовано')->success()->send();
                    }),

                Action::make('reject')
                    ->label('Отклонить')
                    ->icon('heroicon-o-x-circle')
                    ->color('danger')
                    ->visible(fn (Listing $record): bool => in_array(
                        $record->status,
                        [Listing::STATUS_MODERATION, Listing::STATUS_ACTIVE],
                        true,
                    ))
                    ->schema([
                        Textarea::make('reason')
                            ->label('Причина отказа')
                            ->required()
                            ->minLength(10)
                            ->rows(3)
                            // Причина уходит человеку дословно: он должен
                            // понять, что именно исправить
                            ->helperText('Текст увидит владелец объявления. Напишите, что конкретно исправить.'),
                    ])
                    ->action(function (Listing $record, array $data): void {
                        $record->forceFill([
                            'status' => Listing::STATUS_REJECTED,
                            'moderation_note' => $data['reason'],
                        ])->save();

                        app(Notifier::class)->company(
                            $record->company,
                            'moderation',
                            "Объявление «{$record->title}» отклонено",
                            [
                                'tone' => 'danger',
                                'body' => $data['reason'],
                                'url' => '/cabinet/listings?status=rejected',
                            ],
                        );

                        Notification::make()->title('Объявление отклонено')->warning()->send();
                    }),
            ])
            ->toolbarActions([
                BulkActionGroup::make([
                    /*
                     * Ограничение суперадмином — прямо на действии:
                     * canDeleteAny ресурса массовые действия не прячет,
                     * и без visible() модератор мог удалять записи пачкой.
                     */
                    DeleteBulkAction::make()
                        ->visible(fn (): bool => AdminAccess::allows('listings.delete')),
                ]),
            ])
            ->emptyStateHeading('Объявлений нет')
            ->emptyStateDescription('Здесь появятся объявления, отправленные на проверку.');
    }

    /**
     * Отчёт о загрузке.
     *
     * Причины по строкам показываются на месте, а не «скачайте файл
     * с ошибками»: строк в каталоге десятки, и ради двух опечаток
     * ходить за отдельным файлом незачем. Уведомление не гаснет само —
     * иначе отчёт исчезает раньше, чем его успевают прочитать.
     *
     * @param  array{rows: int, created: int, updated: int, photos: int, errors: list<string>}  $result
     */
    private static function report(array $result): void
    {
        $body = 'Обработано строк: '.$result['rows']
            .'. Создано: '.$result['created']
            .', обновлено: '.$result['updated']
            .', фотографий добавлено: '.$result['photos'].'.';

        $errors = array_slice($result['errors'], 0, 10);
        $hidden = count($result['errors']) - count($errors);

        if ($errors !== []) {
            // Причины собраны из ячеек файла: разметку из них убираем,
            // чтобы название товара не приехало в окно как разметка
            $body .= ' — '.implode(' • ', array_map(strip_tags(...), $errors));

            if ($hidden > 0) {
                $body .= ' • и ещё '.$hidden;
            }
        }

        $notification = Notification::make()
            ->title($result['errors'] === [] ? 'Загрузка завершена' : 'Загрузка завершена с ошибками')
            ->body($body)
            ->persistent();

        ($result['errors'] === [] ? $notification->success() : $notification->warning())->send();
    }
}
