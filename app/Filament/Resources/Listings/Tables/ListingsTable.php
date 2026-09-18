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
    /**
     * Сколько книг принимаем за раз.
     *
     * Ограничение не в самой загрузке, а во времени запроса: сервер
     * обрывает его на двух минутах, а пересжатие сотни фотографий
     * занимает десятки секунд. Десять книг по паре сотен строк —
     * потолок, за которым отчёт рискует не дождаться конца.
     */
    private const MAX_WORKBOOKS = 10;

    private const STATUS_LABELS = [
        Listing::STATUS_DRAFT => 'Черновик',
        Listing::STATUS_MODERATION => 'На проверке',
        Listing::STATUS_ACTIVE => 'Активно',
        Listing::STATUS_REJECTED => 'Отклонено',
        Listing::STATUS_EXPIRED => 'Истекло',
        Listing::STATUS_ARCHIVED => 'Снято',
    ];

    private const SOURCE_LABELS = [
        Listing::SOURCE_CABINET => 'Из кабинета',
        Listing::SOURCE_IMPORT => 'Загружено из Excel',
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
                        FileUpload::make('workbooks')
                            ->label('Книги Excel')
                            // Каталог удобнее резать на файлы по разделам,
                            // и загружать их по одному — лишняя работа
                            ->multiple()
                            ->maxFiles(self::MAX_WORKBOOKS)
                            ->storeFiles(false)
                            ->required()
                            ->acceptedFileTypes(['application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'])
                            // Фотографии лежат внутри книги, поэтому файл
                            // тяжелее обычной таблицы на порядок
                            ->maxSize(51200)
                            ->helperText(new HtmlString(
                                'Формат XLSX, можно выбрать сразу несколько файлов (до '.self::MAX_WORKBOOKS.'). '
                                .'В книге до пяти листов, по одному на язык: «Русский», «English», «O‘zbekcha», '
                                .'«中文», «Türkçe» — как в образце. Первая строка листа — названия столбцов, '
                                .'дальше по строке на товар.<br>'
                                .'Русский лист главный: цена, валюта, категория, компания, город и фотографии '
                                .'берутся с него. На остальных листах — заголовок, описание, условия поставки '
                                .'и оплаты на своём языке, строка к строке с русским листом: число строк должно '
                                .'совпадать, иначе книга не примется.<br>'
                                .'Фотографии вставьте прямо в русский лист, в строку своего товара: сколько '
                                .'снимков в строке, столько и попадёт в объявление (до '.Listing::MAX_IMAGES.'). '
                                .'Формат снимков любой, какой открывает Excel.<br>'
                                .'Строка с «Номером» правит объявление с этим номером, без номера — ищется '
                                .'по названию и компании, не нашлось — заводится новое. Новые объявления '
                                .'попадают в «На проверке» — опубликуйте их из списка.<br>'
                                .'Незаполненная ячейка ничего не ломает: пустое поле просто останется пустым. '
                                .'Ячейку, которую загрузка не понимает — категории нет в каталоге, валюты нет '
                                .'у площадки, — она пропустит, а товар загрузит и напишет об этом в отчёте.'
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
                        $files = array_filter(
                            (array) ($data['workbooks'] ?? []),
                            fn (mixed $file): bool => $file instanceof UploadedFile,
                        );

                        if ($files === []) {
                            Notification::make()->title('Файл не получен')->danger()->send();

                            return;
                        }

                        $result = self::importWorkbooks($files, (bool) ($data['replace'] ?? false));

                        // След в журнале: загрузка создаёт записи пачкой,
                        // минуя формы и их проверки
                        AdminLog::record('imported', 'listings', note: 'Книг: '.count($files)
                            .', создано: '.$result['created']
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

                // Модератору полезно видеть, откуда запись: загруженное
                // из книги проверяет тот, кто его загрузил
                TextColumn::make('source')
                    ->label('Источник')
                    ->badge()
                    ->color('gray')
                    ->formatStateUsing(fn (string $state): string => self::SOURCE_LABELS[$state] ?? $state)
                    ->toggleable(isToggledHiddenByDefault: true),

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

                SelectFilter::make('source')
                    ->label('Источник')
                    ->options(self::SOURCE_LABELS),
            ])
            ->recordActions([
                Action::make('approve')
                    ->label('Одобрить')
                    ->icon('heroicon-o-check-circle')
                    ->color('success')
                    ->visible(fn (Listing $record): bool => $record->status === Listing::STATUS_MODERATION
                        && self::canModerate($record))
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
                    ) && self::canModerate($record))
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
     * Кому можно одобрять и отклонять.
     *
     * Модератору — всё. Тому, кто загружает книги, — загруженное:
     * загрузка кладёт объявления в «На проверке», и без этого права
     * администратор загружал бы то, что опубликовать не может.
     */
    private static function canModerate(Listing $record): bool
    {
        return AdminAccess::allows('listings.moderate')
            || ($record->isImported() && AdminAccess::allows('listings.import'));
    }

    /**
     * Разобрать выбранные книги подряд и сложить итоги.
     *
     * @param  list<UploadedFile>  $files
     * @return array{rows: int, created: int, updated: int, photos: int, errors: list<string>, notes: list<string>}
     */
    private static function importWorkbooks(array $files, bool $replace): array
    {
        $total = ['rows' => 0, 'created' => 0, 'updated' => 0, 'photos' => 0, 'errors' => [], 'notes' => []];
        $many = count($files) > 1;

        foreach ($files as $file) {
            // Книга копируется в обычный файл: ZipArchive не умеет
            // читать потоки, а временный диск Livewire не обязан
            // быть локальным
            $copy = (string) tempnam(sys_get_temp_dir(), 'savdex-workbook');
            file_put_contents($copy, $file->get());

            try {
                $result = app(ListingWorkbookImport::class)->run($copy, Auth::user(), $replace);
            } finally {
                @unlink($copy);
            }

            foreach (['rows', 'created', 'updated', 'photos'] as $counter) {
                $total[$counter] += $result[$counter];
            }

            // Из какой книги строка — понятно только когда их несколько
            $prefix = $many ? $file->getClientOriginalName().', ' : '';

            foreach (['errors', 'notes'] as $kind) {
                foreach ($result[$kind] as $line) {
                    $total[$kind][] = $prefix.($many ? lcfirst($line) : $line);
                }
            }
        }

        return $total;
    }

    /**
     * Отчёт о загрузке.
     *
     * Причины по строкам показываются на месте, а не «скачайте файл
     * с ошибками»: строк в каталоге десятки, и ради двух опечаток
     * ходить за отдельным файлом незачем. Уведомление не гаснет само —
     * иначе отчёт исчезает раньше, чем его успевают прочитать.
     *
     * @param  array{rows: int, created: int, updated: int, photos: int, errors: list<string>, notes: list<string>}  $result
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

        /*
         * Заметки — не ошибки: пустой языковой лист и пропущенная
         * ячейка загрузке не мешают, но человек должен знать, чего
         * в загруженном не хватает. Список так же подрезан, как
         * ошибки: пропусков в большом файле бывают сотни, и окно
         * с ними не закрывается до конца экрана.
         */
        $notes = array_slice($result['notes'], 0, 10);

        if ($notes !== []) {
            $body .= ' '.implode(' ', array_map(strip_tags(...), $notes));

            if (($more = count($result['notes']) - count($notes)) > 0) {
                $body .= ' И ещё '.$more.'.';
            }
        }

        $notification = Notification::make()
            ->title($result['errors'] === [] ? 'Загрузка завершена' : 'Загрузка завершена с ошибками')
            ->body($body)
            ->persistent();

        ($result['errors'] === [] ? $notification->success() : $notification->warning())->send();
    }
}
