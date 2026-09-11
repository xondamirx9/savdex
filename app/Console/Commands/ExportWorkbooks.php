<?php

declare(strict_types=1);

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Database\ConnectionInterface;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;
use OpenSpout\Common\Entity\Row;
use OpenSpout\Common\Entity\Style\CellAlignment;
use OpenSpout\Common\Entity\Style\Color;
use OpenSpout\Common\Entity\Style\Style;
use OpenSpout\Reader\XLSX\Reader;
use OpenSpout\Writer\AutoFilter;
use OpenSpout\Writer\XLSX\Entity\SheetView;
use OpenSpout\Writer\XLSX\Writer;
use RuntimeException;
use Throwable;

/**
 * Выгрузка базы в две книги Excel: компании и объявления.
 *
 * Сделана под одну задачу — снять с площадки всё живое перед тем, как
 * вычистить тестовые аккаунты. Поэтому выгружается не витрина, а
 * содержимое таблиц: с идентификаторами, служебными полями и удалёнными
 * записями. По такой выгрузке можно и глазами отличить тестовое от
 * настоящего, и восстановить данные, если вычистили лишнего.
 *
 * Читаемые названия (страна, город, категория, тариф, компания) стоят
 * рядом с идентификаторами, а не вместо них: человеку нужны первые,
 * восстановлению — вторые.
 *
 * Записанное проверяется: файл открывается заново и каждая ячейка
 * сверяется со значением из повторного запроса к базе. Молча испорченная
 * выгрузка хуже отсутствующей — на неё полагаются, когда база уже стёрта.
 */
class ExportWorkbooks extends Command
{
    protected $signature = 'savdex:export-xlsx
        {--dir= : Каталог для файлов (по умолчанию storage/app/exports)}
        {--connection= : Подключение к базе (по умолчанию текущее)}';

    protected $description = 'Выгрузить компании и объявления в два файла Excel со сверкой';

    /** Предел длины ячейки в формате Excel. */
    private const CELL_LIMIT = 32000;

    private int $truncated = 0;

    /** @var array<string, array<int, string>> */
    private array $dictionaries = [];

    public function handle(): int
    {
        $db = DB::connection($this->option('connection') ?: null);

        $dir = rtrim((string) ($this->option('dir') ?: storage_path('app/exports')), '/');

        if (! is_dir($dir) && ! mkdir($dir, 0755, true) && ! is_dir($dir)) {
            $this->error("Не удалось создать каталог {$dir}");

            return self::FAILURE;
        }

        $this->line('База: '.$db->getName().' ('.$db->getDriverName().')');
        $this->line('Каталог: '.$dir);
        $this->newLine();

        $this->loadDictionaries($db);

        $stamp = now()->format('Y-m-d-Hi');

        try {
            $books = [
                [
                    'file' => "{$dir}/savdex-companies-{$stamp}.xlsx",
                    'title' => 'SAVDEX — компании',
                    'about' => 'Компании площадки и всё, что к ним привязано: сотрудники, контакты, документы, кошельки, подписки, раскрытия контактов и отзывы.',
                    'sheets' => $this->companySheets($db),
                ],
                [
                    'file' => "{$dir}/savdex-listings-{$stamp}.xlsx",
                    'title' => 'SAVDEX — объявления',
                    'about' => 'Объявления площадки и всё, что к ним привязано: фотографии, характеристики, статистика по дням, избранное. Отдельным листом — тендеры.',
                    'sheets' => $this->listingSheets($db),
                ],
            ];
        } catch (RuntimeException $e) {
            $this->error($e->getMessage());

            return self::FAILURE;
        }

        $written = [];

        foreach ($books as $book) {
            try {
                $this->write($book);
            } catch (Throwable $e) {
                $this->error('Запись '.basename($book['file']).': '.$e->getMessage());

                return self::FAILURE;
            }

            $this->line('Записано: '.basename($book['file']));
            $written[] = $book;
        }

        $this->newLine();

        return $this->verify($db, $written);
    }

    // ── Листы ───────────────────────────────────────────────────────

    /** @return list<array{name: string, about: string, columns: list<array{0: string, 1: string, 2: string}>, table: string, order: string, rows: list<array<string, mixed>>}> */
    private function companySheets(ConnectionInterface $db): array
    {
        return [
            $this->sheet($db, 'Компании', 'companies',
                'Карточки компаний, включая удалённые. Главный лист книги.', [
                    ['ID', 'id', 'int'],
                    ['Адрес страницы', 'slug', 'text'],
                    ['Название', 'name', 'text'],
                    ['Юридическое название', 'legal_name', 'text'],
                    ['ИНН / СТИР', 'tin', 'text'],
                    ['Страна', '@country', 'text'],
                    ['ID страны', 'country_id', 'int'],
                    ['Город', '@city', 'text'],
                    ['ID города', 'city_id', 'int'],
                    ['Адрес', 'address', 'text'],
                    ['Широта', 'lat', 'float'],
                    ['Долгота', 'lng', 'float'],
                    ['Тип', 'type', 'text'],
                    ['Роль', 'primary_role', 'text'],
                    ['Описание', 'description', 'text'],
                    ['Сайт', 'website', 'text'],
                    ['Телефон', 'phone', 'text'],
                    ['Email', 'email', 'text'],
                    ['Telegram', 'telegram', 'text'],
                    ['WhatsApp', 'whatsapp', 'text'],
                    ['Контактное лицо', 'contact_person', 'text'],
                    ['Год основания', 'founded_year', 'int'],
                    ['Размер штата', 'employees_range', 'text'],
                    ['Оборот', 'turnover_range', 'text'],
                    ['Уровень проверки', 'verification_level', 'int'],
                    ['Проверена', 'verified_at', 'datetime'],
                    ['Кем проверена', '@verified_by', 'text'],
                    ['Рейтинг', 'rating', 'float'],
                    ['Отзывов', 'reviews_count', 'int'],
                    ['Сделок', 'completed_deals_count', 'int'],
                    ['Ответ, часов', 'response_time_hours', 'int'],
                    ['Статус', 'status', 'text'],
                    ['Причина блокировки', 'blocked_reason', 'text'],
                    ['Заблокирована', 'blocked_at', 'datetime'],
                    ['Учётных записей', '@users_count', 'int'],
                    ['Объявлений всего', '@listings_total', 'int'],
                    ['Из них активных', '@listings_active', 'int'],
                    ['Раскрытий контактов', '@unlocks_made', 'int'],
                    ['Своя категория', 'custom_category', 'text'],
                    ['Пометка источника', 'source_note', 'text'],
                    ['Логотип', 'logo_path', 'text'],
                    ['Обложка', 'cover_path', 'text'],
                    ['Создана', 'created_at', 'datetime'],
                    ['Обновлена', 'updated_at', 'datetime'],
                    ['Удалена', 'deleted_at', 'datetime'],
                ]),

            $this->sheet($db, 'Сотрудники', 'users',
                'Учётные записи людей. Здесь видно тестовые регистрации: почта, дата создания, подтверждён ли адрес, был ли вход.', [
                    ['ID', 'id', 'int'],
                    ['Имя', 'name', 'text'],
                    ['Email', 'email', 'text'],
                    ['Email подтверждён', 'email_verified_at', 'datetime'],
                    ['Телефон', 'phone', 'text'],
                    ['Телефон подтверждён', 'phone_verified_at', 'datetime'],
                    ['ID компании', 'company_id', 'int'],
                    ['Компания', '@company', 'text'],
                    ['Роль в компании', 'company_role', 'text'],
                    ['Администратор площадки', 'is_admin', 'bool'],
                    ['Роль администратора', 'admin_role', 'text'],
                    ['Язык', 'locale', 'text'],
                    ['Статус', 'status', 'text'],
                    ['Последний вход', 'last_login_at', 'datetime'],
                    ['IP последнего входа', 'last_login_ip', 'text'],
                    ['Создан', 'created_at', 'datetime'],
                    ['Обновлён', 'updated_at', 'datetime'],
                    ['Удалён', 'deleted_at', 'datetime'],
                ]),

            $this->sheet($db, 'Контакты', 'company_contacts',
                'Дополнительные контакты компаний сверх тех, что лежат в карточке.', [
                    ['ID', 'id', 'int'],
                    ['ID компании', 'company_id', 'int'],
                    ['Компания', '@company', 'text'],
                    ['Вид', 'type', 'text'],
                    ['Значение', 'value', 'text'],
                    ['Подпись', 'label', 'text'],
                    ['Контактное лицо', 'contact_person', 'text'],
                    ['Основной', 'is_primary', 'bool'],
                    ['Публичный', 'is_public', 'bool'],
                    ['Порядок', 'sort_order', 'int'],
                    ['Создан', 'created_at', 'datetime'],
                ]),

            $this->sheet($db, 'Категории компаний', 'company_category',
                'Какая компания в каких разделах каталога. Одна строка — одна связь.', [
                    ['ID', 'id', 'int'],
                    ['ID компании', 'company_id', 'int'],
                    ['Компания', '@company', 'text'],
                    ['ID категории', 'category_id', 'int'],
                    ['Категория', '@category', 'text'],
                    ['Создана', 'created_at', 'datetime'],
                ]),

            $this->sheet($db, 'Документы', 'company_documents',
                'Загруженные компаниями документы. Сами файлы лежат на диске, здесь только их описания и пути.', [
                    ['ID', 'id', 'int'],
                    ['ID компании', 'company_id', 'int'],
                    ['Компания', '@company', 'text'],
                    ['Вид', 'type', 'text'],
                    ['Название', 'title', 'text'],
                    ['Путь к файлу', 'file_path', 'text'],
                    ['Размер, байт', 'file_size', 'int'],
                    ['Тип файла', 'mime', 'text'],
                    ['Действует до', 'valid_until', 'date'],
                    ['Публичный', 'is_public', 'bool'],
                    ['Модерация', 'moderation_status', 'text'],
                    ['Замечание модератора', 'moderation_note', 'text'],
                    ['Создан', 'created_at', 'datetime'],
                ]),

            $this->sheet($db, 'Кошельки', 'wallets',
                'Остатки кредитов на раскрытие контактов и единиц продвижения. Один кошелёк на компанию.', [
                    ['ID', 'id', 'int'],
                    ['ID компании', 'company_id', 'int'],
                    ['Компания', '@company', 'text'],
                    ['Кредиты', 'credits', 'int'],
                    ['Единицы продвижения', 'promo_units', 'int'],
                    ['Контактов за период', 'contacts_used_this_period', 'int'],
                    ['Откликов за период', 'responses_used_this_period', 'int'],
                    ['Период сбросится', 'period_resets_at', 'datetime'],
                    ['Создан', 'created_at', 'datetime'],
                ]),

            $this->sheet($db, 'Подписки', 'subscriptions',
                'Кто на каком тарифе и до какого числа.', [
                    ['ID', 'id', 'int'],
                    ['ID компании', 'company_id', 'int'],
                    ['Компания', '@company', 'text'],
                    ['ID тарифа', 'plan_id', 'int'],
                    ['Тариф', '@plan', 'text'],
                    ['Статус', 'status', 'text'],
                    ['Начало', 'started_at', 'datetime'],
                    ['Окончание', 'ends_at', 'datetime'],
                    ['Автопродление', 'auto_renew', 'bool'],
                    ['Отменена', 'cancelled_at', 'datetime'],
                    ['Источник', 'source', 'text'],
                    ['Основание выдачи', 'grant_reason', 'text'],
                    ['Создана', 'created_at', 'datetime'],
                ]),

            $this->sheet($db, 'Доп. поля компаний', 'company_attributes',
                'Произвольные поля, которые администратор добавляет компаниям без правки схемы.', [
                    ['ID', 'id', 'int'],
                    ['ID компании', 'company_id', 'int'],
                    ['Компания', '@company', 'text'],
                    ['Поле', 'key', 'text'],
                    ['Значение', 'value', 'text'],
                    ['Тип', 'type', 'text'],
                    ['Создано', 'created_at', 'datetime'],
                ]),

            $this->sheet($db, 'Раскрытые контакты', 'contact_unlocks',
                'Кто чьи контакты открыл. Самый honest признак живой компании: за раскрытие платят.', [
                    ['ID', 'id', 'int'],
                    ['ID открывшего', 'company_id', 'int'],
                    ['Кто открыл', '@company', 'text'],
                    ['ID чьи контакты', 'target_company_id', 'int'],
                    ['Чьи контакты', '@target_company', 'text'],
                    ['ID объявления', 'listing_id', 'int'],
                    ['Списано кредитов', 'credits_spent', 'int'],
                    ['Статус работы', 'status', 'text'],
                    ['Заметка', 'note', 'text'],
                    ['Жалоба', 'complaint_status', 'text'],
                    ['Причина жалобы', 'complaint_reason', 'text'],
                    ['Кредит возвращён', 'refunded', 'bool'],
                    ['Создано', 'created_at', 'datetime'],
                ]),

            $this->sheet($db, 'Отзывы', 'reviews',
                'Отзывы компаний друг о друге с оценками по составляющим.', [
                    ['ID', 'id', 'int'],
                    ['ID компании', 'company_id', 'int'],
                    ['О ком отзыв', '@company', 'text'],
                    ['ID автора', 'author_company_id', 'int'],
                    ['Автор', '@author_company', 'text'],
                    ['ID объявления', 'listing_id', 'int'],
                    ['Оценка', 'rating', 'int'],
                    ['Описание товара', 'rating_description', 'int'],
                    ['Ответы', 'rating_response', 'int'],
                    ['Сроки', 'rating_deadlines', 'int'],
                    ['Качество', 'rating_quality', 'int'],
                    ['Текст', 'body', 'text'],
                    ['Сделка подтверждена', 'deal_confirmed', 'bool'],
                    ['Ответ компании', 'reply', 'text'],
                    ['Статус', 'status', 'text'],
                    ['Спор', 'dispute_status', 'text'],
                    ['Создан', 'created_at', 'datetime'],
                ]),
        ];
    }

    /** @return list<array{name: string, about: string, columns: list<array{0: string, 1: string, 2: string}>, table: string, order: string, rows: list<array<string, mixed>>}> */
    private function listingSheets(ConnectionInterface $db): array
    {
        return [
            $this->sheet($db, 'Объявления', 'listings',
                'Объявления площадки, включая черновики и удалённые. Главный лист книги.', [
                    ['ID', 'id', 'int'],
                    ['ID компании', 'company_id', 'int'],
                    ['Компания', '@company', 'text'],
                    ['ID автора', 'user_id', 'int'],
                    ['Автор', '@user', 'text'],
                    ['Вид', 'type', 'text'],
                    ['Адрес страницы', 'slug', 'text'],
                    ['Заголовок', 'title', 'text'],
                    ['Описание', 'description', 'text'],
                    ['ID категории', 'category_id', 'int'],
                    ['Категория', '@category', 'text'],
                    ['ID города', 'city_id', 'int'],
                    ['Город', '@city', 'text'],
                    ['Цена', 'price', 'float'],
                    ['Цена за партию', 'bundle_price', 'float'],
                    ['Валюта', 'currency', 'text'],
                    ['Единица', 'unit', 'text'],
                    ['Цена договорная', 'price_negotiable', 'bool'],
                    ['Минимальный заказ', 'min_order', 'int'],
                    ['Условия доставки', 'delivery_terms', 'text'],
                    ['Условия оплаты', 'payment_terms', 'text'],
                    ['Метки', 'tags', 'text'],
                    ['Статус', 'status', 'text'],
                    ['Замечание модератора', 'moderation_note', 'text'],
                    ['Шаг мастера', 'wizard_step', 'int'],
                    ['Опубликовано', 'published_at', 'datetime'],
                    ['Истекает', 'expires_at', 'datetime'],
                    ['Показов', 'impressions_count', 'int'],
                    ['Просмотров', 'views_count', 'int'],
                    ['Раскрытий контакта', 'unlocks_count', 'int'],
                    ['В избранном', 'favorites_count', 'int'],
                    ['Переводы заголовка', 'title_i18n', 'text'],
                    ['Создано', 'created_at', 'datetime'],
                    ['Обновлено', 'updated_at', 'datetime'],
                    ['Удалено', 'deleted_at', 'datetime'],
                ]),

            $this->sheet($db, 'Фотографии', 'listing_images',
                'Фотографии объявлений. Сами файлы лежат на диске, здесь пути к ним и порядок показа.', [
                    ['ID', 'id', 'int'],
                    ['ID объявления', 'listing_id', 'int'],
                    ['Объявление', '@listing', 'text'],
                    ['Путь к файлу', 'path', 'text'],
                    ['Путь к миниатюре', 'thumb_path', 'text'],
                    ['Порядок', 'sort', 'int'],
                    ['Создана', 'created_at', 'datetime'],
                ]),

            $this->sheet($db, 'Характеристики', 'listing_attributes',
                'Поля объявления, зависящие от категории: марка, сорт, размер и прочее.', [
                    ['ID', 'id', 'int'],
                    ['ID объявления', 'listing_id', 'int'],
                    ['Объявление', '@listing', 'text'],
                    ['Поле', 'key', 'text'],
                    ['Значение', 'value', 'text'],
                    ['Создано', 'created_at', 'datetime'],
                ]),

            $this->sheet($db, 'Статистика по дням', 'listing_stats',
                'По одной строке на объявление и день. Отсюда строятся графики в кабинете.', [
                    ['ID', 'id', 'int'],
                    ['ID объявления', 'listing_id', 'int'],
                    ['Объявление', '@listing', 'text'],
                    ['Дата', 'date', 'date'],
                    ['Показов', 'impressions', 'int'],
                    ['Просмотров', 'views', 'int'],
                    ['В избранное', 'favorites', 'int'],
                    ['Раскрытий', 'unlocks', 'int'],
                ]),

            $this->sheet($db, 'Избранное', 'favorites',
                'Кто какие объявления сохранил. Шаг воронки между просмотром и раскрытием контакта.', [
                    ['ID', 'id', 'int'],
                    ['ID пользователя', 'user_id', 'int'],
                    ['Пользователь', '@user', 'text'],
                    ['ID объявления', 'listing_id', 'int'],
                    ['Объявление', '@listing', 'text'],
                    ['Добавлено', 'created_at', 'datetime'],
                ]),

            $this->sheet($db, 'Тендеры', 'tenders',
                'Закупки, заведённые отдельно от объявлений: со своим заказчиком, бюджетом и сроком подачи.', [
                    ['ID', 'id', 'int'],
                    ['Адрес страницы', 'slug', 'text'],
                    ['Заголовок', 'title', 'text'],
                    ['Описание', 'description', 'text'],
                    ['Заказчик', 'customer', 'text'],
                    ['ID категории', 'category_id', 'int'],
                    ['Категория', '@category', 'text'],
                    ['ID страны', 'country_id', 'int'],
                    ['Страна', '@country', 'text'],
                    ['Место', 'location', 'text'],
                    ['Бюджет', 'budget', 'float'],
                    ['Валюта', 'currency', 'text'],
                    ['Приём до', 'deadline_at', 'datetime'],
                    ['Источник', 'source_url', 'text'],
                    ['Контактное лицо', 'contact_name', 'text'],
                    ['Телефон', 'contact_phone', 'text'],
                    ['Email', 'contact_email', 'text'],
                    ['Статус', 'status', 'text'],
                    ['Опубликован', 'published_at', 'datetime'],
                    ['Просмотров', 'views_count', 'int'],
                    ['Создан', 'created_at', 'datetime'],
                ]),
        ];
    }

    // ── Сбор данных ─────────────────────────────────────────────────

    /**
     * Один лист: описание, колонки и уже собранные строки.
     *
     * Через построитель запросов, а не через модели: у компаний и
     * объявлений есть мягкое удаление, и Eloquent молча спрятал бы
     * удалённые строки — ровно те, ради которых выгрузка и делается.
     *
     * @param  list<array{0: string, 1: string, 2: string}>  $columns
     * @return array{name: string, about: string, columns: list<array{0: string, 1: string, 2: string}>, table: string, order: string, rows: list<array<string, mixed>>}
     */
    private function sheet(ConnectionInterface $db, string $name, string $table, string $about, array $columns): array
    {
        $this->assertColumnsSane($db, $name, $table, $columns);

        return [
            'name' => $name,
            'about' => $about,
            'table' => $table,
            'order' => 'id',
            'columns' => $columns,
            'rows' => $this->fetch($db, $table, $columns),
        ];
    }

    /**
     * Описание листа не должно врать о таблице.
     *
     * Две проверки, каждая — по следам поймавшей меня ошибки. Строка
     * собирается в массив по заголовку, и два одинаковых заголовка
     * затирают друг друга: колонок остаётся на одну меньше, всё правее
     * съезжает влево, а последний столбец выходит пустым. Опечатка же в
     * имени поля не ломает ничего — она молча даёт пустой столбец,
     * который на выгрузке перед очисткой базы выглядит как «данных нет».
     *
     * @param  list<array{0: string, 1: string, 2: string}>  $columns
     */
    private function assertColumnsSane(ConnectionInterface $db, string $name, string $table, array $columns): void
    {
        $headers = array_map(static fn (array $c): string => $c[0], $columns);
        $duplicates = array_keys(array_filter(array_count_values($headers), static fn (int $n): bool => $n > 1));

        if ($duplicates !== []) {
            throw new RuntimeException("Лист «{$name}»: заголовки повторяются — ".implode(', ', $duplicates));
        }

        $existing = Schema::connection($db->getName())->getColumnListing($table);

        foreach ($columns as [$header, $key]) {
            if (! str_starts_with($key, '@') && ! in_array($key, $existing, true)) {
                throw new RuntimeException("Лист «{$name}»: в таблице {$table} нет поля «{$key}» (колонка «{$header}»)");
            }
        }
    }

    /**
     * Строки таблицы, приведённые к значениям ячеек.
     *
     * @param  list<array{0: string, 1: string, 2: string}>  $columns
     * @return list<array<string, mixed>>
     */
    private function fetch(ConnectionInterface $db, string $table, array $columns): array
    {
        $rows = [];
        $expected = count($columns);

        foreach ($db->table($table)->orderBy('id')->cursor() as $record) {
            $record = (array) $record;
            $row = [];

            foreach ($columns as [$header, $key, $kind]) {
                $row[$header] = str_starts_with($key, '@')
                    ? $this->lookup($key, $record)
                    : $this->cell($record[$key] ?? null, $kind);
            }

            if (count($row) !== $expected) {
                throw new RuntimeException(
                    "Таблица {$table}: в строке {$expected} колонок по описанию, а собралось ".count($row)
                );
            }

            $rows[] = $row;
        }

        return $rows;
    }

    /**
     * Читаемое название вместо идентификатора.
     *
     * @param  array<string, mixed>  $record
     */
    private function lookup(string $key, array $record): string|int
    {
        [$dictionary, $field] = match ($key) {
            '@users_count' => ['users_count', 'id'],
            '@listings_total' => ['listings_total', 'id'],
            '@listings_active' => ['listings_active', 'id'],
            '@unlocks_made' => ['unlocks_made', 'id'],
            '@country' => ['countries', 'country_id'],
            '@city' => ['cities', 'city_id'],
            '@category' => ['categories', 'category_id'],
            '@company' => ['companies', 'company_id'],
            '@target_company' => ['companies', 'target_company_id'],
            '@author_company' => ['companies', 'author_company_id'],
            '@user' => ['users', 'user_id'],
            '@verified_by' => ['users', 'verified_by'],
            '@plan' => ['plans', 'plan_id'],
            '@listing' => ['listings', 'listing_id'],
            default => ['', ''],
        };

        $id = $record[$field] ?? null;

        if ($id === null || $dictionary === '') {
            return '';
        }

        // Счётчик, которого нет в справочнике, — это ноль, а не пустая
        // ячейка: «объявлений нет» и «не считали» читаются по-разному,
        // а решение удалять компанию принимают именно по этому числу
        $value = $this->dictionaries[$dictionary][(int) $id] ?? null;

        if (str_ends_with($dictionary, '_count') || str_contains($dictionary, 'listings_') || $dictionary === 'unlocks_made') {
            return (int) ($value ?? 0);
        }

        return (string) ($value ?? '');
    }

    /** Значение ячейки: тип задан колонкой, а не угадывается по виду. */
    private function cell(mixed $value, string $kind): string|int|float
    {
        if ($value === null || $value === '') {
            return '';
        }

        return match ($kind) {
            'int' => (int) $value,
            'float' => (float) $value,
            'bool' => ((bool) $value && $value !== 'f') ? 'да' : 'нет',
            'date' => substr($this->text($value), 0, 10),
            'datetime' => substr(str_replace('T', ' ', $this->text($value)), 0, 19),
            default => $this->text($value),
        };
    }

    /**
     * Текст ячейки.
     *
     * Телефоны, ИНН и адреса страниц остаются строками намеренно: Excel
     * превращает «00998…» в число и съедает ведущие нули, а выгрузка
     * делается как раз затем, чтобы ничего не потерялось.
     */
    private function text(mixed $value): string
    {
        $text = is_array($value) ? json_encode($value, JSON_UNESCAPED_UNICODE) : (string) $value;

        if (mb_strlen($text) > self::CELL_LIMIT) {
            $this->truncated++;

            return mb_substr($text, 0, self::CELL_LIMIT).' […обрезано]';
        }

        return $text;
    }

    /** Справочники для читаемых названий. */
    private function loadDictionaries(ConnectionInterface $db): void
    {
        $this->dictionaries = [
            'countries' => $this->translations($db, 'country_translations', 'country_id'),
            'cities' => $this->translations($db, 'city_translations', 'city_id'),
            'categories' => $this->translations($db, 'category_translations', 'category_id'),
            'companies' => $this->column($db, 'companies', 'name'),
            'users' => $this->column($db, 'users', 'email'),
            'plans' => $this->column($db, 'plans', 'name'),
            'listings' => $this->column($db, 'listings', 'title'),

            // Живую компанию от тестовой отличает не карточка, а след:
            // сколько у неё людей, объявлений и оплаченных раскрытий
            'users_count' => $this->counts($db, 'users', 'company_id'),
            'listings_total' => $this->counts($db, 'listings', 'company_id'),
            'listings_active' => $this->counts($db, 'listings', 'company_id', ['status' => 'active']),
            'unlocks_made' => $this->counts($db, 'contact_unlocks', 'company_id'),
        ];
    }

    /**
     * Сколько строк таблицы приходится на каждое значение колонки.
     *
     * Подсчёт в PHP, а не запросом с GROUP BY: выгрузка должна работать
     * одинаково на SQLite и на PostgreSQL, а таблицы здесь такого
     * размера, что разница незаметна.
     *
     * @param  array<string, mixed>  $where
     * @return array<int, int>
     */
    private function counts(ConnectionInterface $db, string $table, string $column, array $where = []): array
    {
        $counts = [];

        $query = $db->table($table)->select($column);

        foreach ($where as $field => $value) {
            $query->where($field, $value);
        }

        foreach ($query->cursor() as $row) {
            $id = ((array) $row)[$column] ?? null;

            if ($id !== null) {
                $counts[(int) $id] = ($counts[(int) $id] ?? 0) + 1;
            }
        }

        return $counts;
    }

    /**
     * Названия из таблицы переводов: русский, иначе любой имеющийся.
     *
     * @return array<int, string>
     */
    private function translations(ConnectionInterface $db, string $table, string $key): array
    {
        $names = [];

        foreach ($db->table($table)->orderBy('id')->get() as $row) {
            $row = (array) $row;
            $id = (int) $row[$key];

            if ($row['locale'] === 'ru' || ! isset($names[$id])) {
                $names[$id] = (string) $row['name'];
            }
        }

        return $names;
    }

    /** @return array<int, string> */
    private function column(ConnectionInterface $db, string $table, string $field): array
    {
        $values = [];

        foreach ($db->table($table)->select('id', $field)->cursor() as $row) {
            $row = (array) $row;
            $values[(int) $row['id']] = (string) ($row[$field] ?? '');
        }

        return $values;
    }

    // ── Запись ──────────────────────────────────────────────────────

    /** @param array{file: string, title: string, about: string, sheets: list<array<string, mixed>>} $book */
    private function write(array $book): void
    {
        $writer = new Writer;
        $writer->setCreator('SAVDEX');
        $writer->openToFile($book['file']);

        $this->writeLegend($writer, $book);

        foreach ($book['sheets'] as $sheet) {
            $this->writeSheet($writer, $sheet);
        }

        $writer->close();
    }

    /**
     * Первый лист — путеводитель по книге: что на каком листе и сколько
     * там строк. Без него человек открывает файл на десять вкладок и
     * гадает, чем «Контакты» отличаются от «Доп. полей».
     *
     * @param  array{file: string, title: string, about: string, sheets: list<array<string, mixed>>}  $book
     */
    private function writeLegend(Writer $writer, array $book): void
    {
        $sheet = $writer->getCurrentSheet();
        $sheet->setName('Справка');
        $sheet->setColumnWidth(34, 1);
        $sheet->setColumnWidth(96, 2);
        $sheet->setColumnWidth(12, 3);

        $title = (new Style)->setFontBold()->setFontSize(16);
        $muted = (new Style)->setFontColor('595959');
        $head = (new Style)
            ->setFontBold()
            ->setFontColor(Color::WHITE)
            ->setBackgroundColor('2E5C86')
            ->setCellVerticalAlignment(CellAlignment::CENTER);

        $writer->addRow(Row::fromValues([$book['title']], $title));
        $writer->addRow(Row::fromValues([$book['about']], $muted));
        $writer->addRow(Row::fromValues([]));
        $writer->addRow(Row::fromValues(['Выгружено', now()->format('d.m.Y H:i')], $muted));
        $writer->addRow(Row::fromValues(['Всего листов с данными', count($book['sheets'])], $muted));
        $writer->addRow(Row::fromValues([
            'Всего строк',
            array_sum(array_map(static fn (array $s): int => count($s['rows']), $book['sheets'])),
        ], $muted));
        $writer->addRow(Row::fromValues([]));
        $writer->addRow(Row::fromValues(['Лист', 'Что содержит', 'Строк'], $head));

        foreach ($book['sheets'] as $s) {
            $writer->addRow(Row::fromValues([$s['name'], $s['about'], count($s['rows'])]));
        }

        $writer->addRow(Row::fromValues([]));
        $writer->addRow(Row::fromValues([
            'Как читать',
            'Рядом с каждым «ID …» стоит читаемое название. Идентификаторы нужны, чтобы связать листы между собой и восстановить данные; названия — чтобы читать глазами. Пустая ячейка означает, что значения в базе нет.',
        ], $muted));
        $writer->addRow(Row::fromValues([
            '',
            'Столбцы «Удалена» и «Удалено» заполнены у записей, скрытых с сайта, но не стёртых из базы. В выгрузку они включены намеренно.',
        ], $muted));
    }

    /** @param array<string, mixed> $sheet */
    private function writeSheet(Writer $writer, array $sheet): void
    {
        $page = $writer->addNewSheetAndMakeItCurrent();
        $page->setName($sheet['name']);

        $headers = array_map(static fn (array $c): string => $c[0], $sheet['columns']);

        $head = (new Style)
            ->setFontBold()
            ->setFontColor(Color::WHITE)
            ->setBackgroundColor('2E5C86')
            ->setShouldWrapText(false)
            ->setCellVerticalAlignment(CellAlignment::CENTER);

        $writer->addRow(Row::fromValues($headers, $head));

        foreach ($sheet['rows'] as $row) {
            $writer->addRow(Row::fromValues(array_values($row)));
        }

        // Шапка остаётся на экране при прокрутке, а фильтр позволяет
        // отобрать, например, все объявления одной компании
        $page->setSheetView((new SheetView)->setFreezeRow(2));

        if ($sheet['rows'] !== []) {
            $page->setAutoFilter(new AutoFilter(0, 1, count($headers) - 1, count($sheet['rows']) + 1));
        }

        foreach ($sheet['columns'] as $index => [$header, $key, $kind]) {
            $page->setColumnWidth($this->width($header, $kind), $index + 1);
        }
    }

    /** Ширина колонки по её роли: даты и числа узкие, тексты широкие. */
    private function width(string $header, string $kind): float
    {
        return match (true) {
            str_starts_with($header, 'ID') => 9,
            $kind === 'int', $kind === 'float', $kind === 'bool' => 14,
            $kind === 'date' => 12,
            $kind === 'datetime' => 19,
            in_array($header, ['Описание', 'Текст', 'Замечание модератора', 'Заметка'], true) => 60,
            default => 26,
        };
    }

    // ── Сверка ──────────────────────────────────────────────────────

    /**
     * Файл открывается заново и сверяется с базой.
     *
     * Сверяется не с тем массивом, из которого писали, а с повторным
     * запросом: иначе проверка подтвердила бы сама себя. Отдельно
     * сверяются наборы идентификаторов — так видно пропавшую строку,
     * даже если их число случайно совпало.
     *
     * @param  list<array{file: string, title: string, about: string, sheets: list<array<string, mixed>>}>  $books
     */
    private function verify(ConnectionInterface $db, array $books): int
    {
        $this->line('Сверка записанного с базой…');
        $this->newLine();

        $problems = [];
        $report = [];

        foreach ($books as $book) {
            $onDisk = $this->read($book['file']);

            foreach ($book['sheets'] as $sheet) {
                $name = $sheet['name'];
                $table = $sheet['table'];
                $expected = $this->fetch($db, $table, $sheet['columns']);
                $actual = $onDisk[$name] ?? null;

                if ($actual === null) {
                    $problems[] = "{$name}: листа нет в файле";

                    continue;
                }

                $headers = array_map(static fn (array $c): string => $c[0], $sheet['columns']);
                $inDatabase = (int) $db->table($table)->count();

                if (array_shift($actual) !== $headers) {
                    $problems[] = "{$name}: шапка в файле не совпадает с ожидаемой";
                }

                if (count($actual) !== count($expected) || count($expected) !== $inDatabase) {
                    $problems[] = sprintf(
                        '%s: строк в базе %d, собрано %d, в файле %d',
                        $name, $inDatabase, count($expected), count($actual)
                    );

                    continue;
                }

                $mismatch = $this->compare($name, $headers, $expected, $actual);
                $problems = array_merge($problems, $mismatch);

                $report[] = [
                    basename($book['file']),
                    $name,
                    $inDatabase,
                    $mismatch === [] ? 'сходится' : 'РАСХОЖДЕНИЕ',
                ];
            }
        }

        $this->table(['Файл', 'Лист', 'Строк', 'Сверка'], $report);
        $this->newLine();

        if ($this->truncated > 0) {
            $this->warn("Значений, обрезанных до предела Excel: {$this->truncated}. Они помечены в ячейке.");
        }

        if ($problems !== []) {
            $this->error('Расхождения ('.count($problems).'):');

            foreach (array_slice($problems, 0, 20) as $problem) {
                $this->line('  '.$problem);
            }

            return self::FAILURE;
        }

        $this->info('Все листы сошлись: число строк, шапки, наборы идентификаторов и каждая ячейка.');

        foreach ($books as $book) {
            $this->line('  '.$book['file'].'  ('.$this->size($book['file']).')');
        }

        return self::SUCCESS;
    }

    /**
     * Построчная сверка листа.
     *
     * @param  list<string>  $headers
     * @param  list<array<string, mixed>>  $expected
     * @param  list<list<mixed>>  $actual
     * @return list<string>
     */
    private function compare(string $name, array $headers, array $expected, array $actual): array
    {
        $problems = [];
        $idColumn = array_search('ID', $headers, true);

        if ($idColumn !== false) {
            $fromDatabase = array_map(static fn (array $r): string => (string) $r['ID'], $expected);
            $fromFile = array_map(static fn (array $r): string => (string) ($r[$idColumn] ?? ''), $actual);

            $missing = array_diff($fromDatabase, $fromFile);
            $extra = array_diff($fromFile, $fromDatabase);

            if ($missing !== []) {
                $problems[] = "{$name}: в файле нет записей с ID ".implode(', ', array_slice($missing, 0, 5));
            }

            if ($extra !== []) {
                $problems[] = "{$name}: в файле лишние ID ".implode(', ', array_slice($extra, 0, 5));
            }
        }

        foreach ($expected as $index => $row) {
            $line = $actual[$index] ?? [];
            $position = 0;

            foreach ($row as $header => $value) {
                $written = $line[$position] ?? null;
                $position++;

                if ($this->same($value, $written)) {
                    continue;
                }

                $problems[] = sprintf(
                    '%s строка %d, «%s»: в базе [%s], в файле [%s]',
                    $name, $index + 2, $header,
                    mb_substr((string) $value, 0, 40),
                    mb_substr(is_scalar($written) ? (string) $written : gettype($written), 0, 40)
                );

                if (count($problems) > 40) {
                    return $problems;
                }
            }
        }

        return $problems;
    }

    /**
     * Совпадают ли значение из базы и прочитанное из файла.
     *
     * Excel не хранит пустую ячейку и отдаёт её как пустую строку, число
     * приходит как float, а дата — как объект. Сравнение приводит обе
     * стороны к одному виду, иначе сверка тонула бы в ложных тревогах.
     */
    private function same(mixed $expected, mixed $written): bool
    {
        if ($written instanceof \DateTimeInterface) {
            $written = $written->format('Y-m-d H:i:s');
        }

        if (is_float($expected) || is_float($written)) {
            if (($expected === '' || $expected === null) !== ($written === '' || $written === null)) {
                return false;
            }

            return abs((float) $expected - (float) $written) < 0.0000001;
        }

        return (string) $expected === (string) ($written ?? '');
    }

    /**
     * Содержимое книги: лист → строки значений.
     *
     * @return array<string, list<list<mixed>>>
     */
    private function read(string $file): array
    {
        $reader = new Reader;
        $reader->open($file);

        $sheets = [];

        foreach ($reader->getSheetIterator() as $sheet) {
            $rows = [];

            foreach ($sheet->getRowIterator() as $row) {
                $rows[] = $row->toArray();
            }

            $sheets[$sheet->getName()] = $rows;
        }

        $reader->close();

        return $sheets;
    }

    private function size(string $file): string
    {
        $bytes = (int) filesize($file);

        return $bytes > 1048576
            ? round($bytes / 1048576, 1).' МБ'
            : round($bytes / 1024).' КБ';
    }
}
