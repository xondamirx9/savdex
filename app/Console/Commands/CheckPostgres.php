<?php

declare(strict_types=1);

namespace App\Console\Commands;

use Illuminate\Console\Command;
use Illuminate\Database\ConnectionInterface;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;
use Throwable;

/**
 * Проверка новой базы PostgreSQL до того, как в неё поедут данные.
 *
 * Базу создаёт человек в панели Render, и ошибиться там легко: не тот
 * тариф, не та переменная, случайно переключённый сайт. Ошибка вылезает
 * не сразу, а на переносе данных — когда откатываться дороже.
 *
 * Команда отвечает на один вопрос: можно ли переносить данные. Что
 * видно из SQL — проверяется; что видно только в панели (регион, тариф,
 * бэкапы, список доступа) — перечислено отдельным списком, потому что
 * «проверено» и «проверить нечем» человек должен различать.
 */
class CheckPostgres extends Command
{
    protected $signature = 'savdex:check-postgres
        {--to=pgsql_target : Подключение к новой базе}';

    protected $description = 'Проверить новую базу PostgreSQL перед переносом данных';

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
        $this->checkSiteStillOnSqlite();
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
     * Сайт на этом шаге обязан остаться на SQLite.
     *
     * Переключение — отдельный шаг, и только после переноса данных.
     * Переключённый раньше времени сайт показывает пустой каталог, а
     * всё, что посетители успеют создать, потом сотрёт перенос.
     */
    private function checkSiteStillOnSqlite(): void
    {
        $driver = DB::connection()->getDriverName();

        if ($driver === 'pgsql') {
            $this->problem('Сайт работает на', 'PostgreSQL',
                'Сайт уже переключён на новую базу, а данные ещё не перенесены. Верните DB_CONNECTION к прежнему значению, пока посетители не начали писать в пустую базу.');

            return;
        }

        $this->ok('Сайт работает на', $driver.' — как и должен на этом шаге');
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
                'Это нормально. Схему создаст «php artisan migrate --database='.$db->getName().' --force», когда дойдёте до переноса.');

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
            $this->ok('Данные', 'база пуста — как и задумано на этом шаге');

            return;
        }

        $this->note('Данные', $this->plural($companies, 'компания', 'компании', 'компаний').
            ', '.$this->plural($listings, 'объявление', 'объявления', 'объявлений'),
            'В базе уже что-то есть. Если это демо-данные от первого запуска, перенос с --truncate их уберёт.');
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
            $this->error('Переносить данные пока нельзя — сначала устраните отмеченное.');

            return self::FAILURE;
        }

        $this->info('База готова. Данные можно переносить, когда закончите с выгрузкой и очисткой.');

        return self::SUCCESS;
    }
}
