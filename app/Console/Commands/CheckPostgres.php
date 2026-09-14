<?php

declare(strict_types=1);

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Database\ConnectionInterface;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;
use Throwable;

/**
 * Проверка базы PostgreSQL: доступна ли, та ли, и что в ней лежит.
 *
 * Базу заводит человек в панели Render, и ошибиться там легко: не тот
 * адрес, не те права, не та база. Ошибка вылезает не сразу, а в момент,
 * когда на базу уже полагаются.
 *
 * Отдельно сверяется, смотрят ли сайт и переменная TARGET_DB_URL в одну
 * и ту же базу. Две базы в обороте — источник самых дорогих недоразумений:
 * данные пишутся в одну, а смотрят и чистят другую.
 *
 * Что видно из SQL — проверяется; что видно только в панели (регион,
 * тариф, бэкапы, список доступа) — перечислено отдельным списком, потому
 * что «проверено» и «проверить нечем» человек должен различать.
 */
class CheckPostgres extends Command
{
    protected $signature = 'savdex:check-postgres
        {--to=pgsql_target : Подключение к новой базе}';

    protected $description = 'Проверить базу PostgreSQL: доступность, права, схему и данные';

    /** @var list<array{string, string, string}> */
    private array $rows = [];

    /** @var list<string> */
    private array $advice = [];

    private bool $blocked = false;

    public function handle(): int
    {
        $name = (string) $this->option('to');

        $this->line('Проверка новой базы, подключение «'.$name.'».');
        $this->newLine();

        $url = (string) (config("database.connections.{$name}.url") ?? '');

        if ($url === '') {
            $this->problem('Адрес базы', 'переменная TARGET_DB_URL пуста',
                'Скопируйте Internal Database URL со вкладки Connect новой базы и задайте её сервису.');

            return $this->report();
        }

        $this->ok('Адрес базы', 'задан');

        try {
            $db = DB::connection($name);
            $db->getPdo();
        } catch (Throwable $e) {
            $this->problem('Соединение', 'не установлено', $this->reason($e->getMessage()));

            return $this->report();
        }

        $this->describe($db);
        $this->compareWithSiteDatabase($db);
        $this->checkPrivileges($db);
        $this->checkSchema($db);

        return $this->report();
    }

    /** Что это за база: версия, имя, пользователь. */
    private function describe(ConnectionInterface $db): void
    {
        if ($db->getDriverName() !== 'pgsql') {
            $this->problem('Тип базы', $db->getDriverName(),
                'Подключение ведёт не в PostgreSQL. Проверьте адрес: он начинается с postgres:// или postgresql://.');

            return;
        }

        $version = (string) $db->scalar('show server_version');

        $this->ok('Соединение', 'PostgreSQL '.$version);
        $this->ok('База и пользователь', (string) $db->scalar('select current_database()').' / '.$db->scalar('select current_user'));
    }

    /**
     * Смотрят ли сайт и проверяемое подключение в одну базу.
     *
     * Две базы в обороте — самая дорогая из возможных путаниц: данные
     * копятся в одной, а выгружают и чистят другую, и расхождение
     * замечают, когда удалённого уже не вернуть. Поэтому здесь сверяются
     * не настройки, а то, что реально ответил сервер на оба подключения.
     */
    private function compareWithSiteDatabase(ConnectionInterface $db): void
    {
        $site = DB::connection();
        $driver = $site->getDriverName();

        if ($driver !== 'pgsql') {
            $this->note('Сайт работает на', $driver,
                'Сайт читает и пишет не ту базу, которую мы проверяем. Если так и задумано, всё в порядке; если нет — проверьте DB_CONNECTION и DB_URL у сервиса.');

            return;
        }

        try {
            $siteDatabase = (string) $site->scalar('select current_database()');
            $siteHost = (string) $site->scalar('select inet_server_addr()');
        } catch (Throwable $e) {
            $this->note('Сайт работает на', 'PostgreSQL', 'Имя базы сайта получить не удалось: '.$this->reason($e->getMessage()));

            return;
        }

        $targetDatabase = (string) $db->scalar('select current_database()');
        $targetHost = (string) $db->scalar('select inet_server_addr()');

        if ($siteDatabase === $targetDatabase && $siteHost === $targetHost) {
            $this->ok('Сайт и проверка', 'смотрят в одну базу — '.$siteDatabase);

            return;
        }

        $this->note('Сайт и проверка', "сайт: {$siteDatabase}, проверка: {$targetDatabase}",
            'Это две разные базы. Убедитесь, что выгружаете и чистите ту, в которую сайт пишет на самом деле.');
    }

    /** Прав должно хватать на создание схемы: миграции их потребуют. */
    private function checkPrivileges(ConnectionInterface $db): void
    {
        try {
            $db->statement('create table if not exists savdex_probe (id int)');
            $db->statement('drop table if exists savdex_probe');
        } catch (Throwable $e) {
            $this->problem('Права', 'создать таблицу не удалось', $this->reason($e->getMessage()));

            return;
        }

        $this->ok('Права', 'создание таблиц разрешено');
    }

    /**
     * Схема и данные.
     *
     * Пустая база на этом шаге — это норма, а не сбой: данные переезжают
     * позже, после того как из них вычистят тестовые аккаунты.
     */
    private function checkSchema(ConnectionInterface $db): void
    {
        $tables = count(Schema::connection($db->getName())->getTables());

        if ($tables === 0) {
            $this->note('Схема', 'таблиц нет',
                'Схему создаёт «php artisan migrate --database='.$db->getName().' --force». Для рабочей базы пустая схема — это ошибка.');

            return;
        }

        $this->ok('Схема', $this->plural($tables, 'таблица', 'таблицы', 'таблиц'));

        if (! Schema::connection($db->getName())->hasTable('companies')) {
            $this->note('Данные', 'таблицы companies нет', 'Схема прогнана не полностью — повторите migrate.');

            return;
        }

        $companies = (int) $db->table('companies')->count();
        $listings = Schema::connection($db->getName())->hasTable('listings')
            ? (int) $db->table('listings')->count()
            : 0;

        if ($companies === 0 && $listings === 0) {
            $this->note('Данные', 'база пуста',
                'Ни компаний, ни объявлений. Для только что созданной базы это норма; для рабочей — повод разобраться, туда ли смотрит сайт.');

            return;
        }

        $this->ok('Данные', $this->plural($companies, 'компания', 'компании', 'компаний').
            ', '.$this->plural($listings, 'объявление', 'объявления', 'объявлений'));
    }

    // ── Отчёт ───────────────────────────────────────────────────────

    private function ok(string $what, string $value): void
    {
        $this->rows[] = ['✓', $what, $value];
    }

    private function note(string $what, string $value, string $advice): void
    {
        $this->rows[] = ['•', $what, $value];
        $this->advice[] = $advice;
    }

    private function problem(string $what, string $value, string $advice): void
    {
        $this->rows[] = ['✗', $what, $value];
        $this->advice[] = $advice;
        $this->blocked = true;
    }

    /** «1 таблица», «2 таблицы», «5 таблиц» — иначе отчёт читается неряшливо. */
    private function plural(int $count, string $one, string $few, string $many): string
    {
        $mod100 = $count % 100;
        $mod10 = $count % 10;

        $word = match (true) {
            $mod100 >= 11 && $mod100 <= 14 => $many,
            $mod10 === 1 => $one,
            $mod10 >= 2 && $mod10 <= 4 => $few,
            default => $many,
        };

        return $count.' '.$word;
    }

    /** Понятная причина вместо простыни драйвера. */
    private function reason(string $message): string
    {
        return match (true) {
            str_contains($message, 'password authentication failed') => 'Пароль в адресе не подошёл. Скопируйте Internal Database URL заново — он содержит пароль целиком.',
            str_contains($message, 'could not translate host name'), str_contains($message, 'Name or service not known') => 'Адрес не резолвится. Изнутри Render нужен Internal Database URL, снаружи — External.',
            str_contains($message, 'Connection refused'), str_contains($message, 'timeout') => 'База не отвечает. Проверьте, что её статус Available, а ваш адрес есть в списке Access Control.',
            str_contains($message, 'does not exist') => 'Базы с таким именем нет. Проверьте имя в адресе.',
            str_contains($message, 'permission denied') => 'Пользователю не хватает прав. Подключайтесь под владельцем базы, которого создал Render.',
            default => mb_substr($message, 0, 160),
        };
    }

    private function report(): int
    {
        $this->table(['', 'Что', 'Состояние'], $this->rows);

        if ($this->advice !== []) {
            $this->newLine();

            foreach ($this->advice as $line) {
                $this->line('  '.$line);
            }
        }

        $this->newLine();
        $this->line('Из SQL не видно, это смотрите в панели Render:');
        $this->line('  • регион базы совпадает с регионом сервиса (потом не поменять);');
        $this->line('  • тариф платный, с бэкапами (бесплатная база удаляется через 30 дней);');
        $this->line('  • в Access Control только нужные адреса, без 0.0.0.0/0.');
        $this->newLine();

        if ($this->blocked) {
            $this->error('База к работе не готова — сначала устраните отмеченное.');

            return self::FAILURE;
        }

        $this->info('База доступна, права на месте, схема и данные читаются.');

        return self::SUCCESS;
    }
}
