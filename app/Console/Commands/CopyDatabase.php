<?php

declare(strict_types=1);

namespace App\Console\Commands;

use Generator;
use Illuminate\Console\Command;
use Illuminate\Database\ConnectionInterface;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Schema;
use Throwable;

/**
 * Перенос данных между подключениями: SQLite → PostgreSQL.
 *
 * Схему создаёт `php artisan migrate` на приёмнике, а не эта команда и не
 * внешний конвертер. Конвертер выводит типы из значений SQLite, где нет
 * ни boolean, ни json: `is_active` приехал бы числом, `tags` — текстом,
 * и `where('is_active', true)` на PostgreSQL упал бы с несовпадением типов.
 *
 * Три вещи, без которых перенос молча портит базу:
 *
 * 1. Порядок таблиц по внешним ключам — родитель раньше ребёнка.
 *    Связи, замкнутые в кольцо (users.company_id → companies,
 *    companies.verified_by → users), разрываются: колонка вставляется
 *    пустой и заполняется вторым проходом. Выключить проверку ключей
 *    нельзя — на Render у приложения нет прав суперпользователя, а
 *    SET CONSTRAINTS ALL DEFERRED молча не трогает недеферрабельные
 *    ограничения Laravel.
 *
 * 2. Булевы значения. SQLite отдаёт 0 и 1, PostgreSQL на вставке
 *    целого в boolean падает. Колонки узнаются по схеме приёмника,
 *    а не по виду значения: 1 в `verification_level` не булево.
 *
 * 3. Счётчики последовательностей. PostgreSQL ведёт их отдельно от
 *    данных: после вставки строк с готовыми id счётчик остаётся на
 *    единице, и первое же новое объявление падает с «duplicate key».
 */
class CopyDatabase extends Command
{
    protected $signature = 'savdex:copy-database
        {--from=sqlite_source : Подключение-источник}
        {--to=pgsql_target : Подключение-приёмник}
        {--chunk=500 : Размер порции строк}
        {--truncate : Очистить таблицы приёмника перед переносом}';

    protected $description = 'Скопировать данные из одной базы в другую (SQLite → PostgreSQL)';

    /**
     * Таблицы, которые не переносятся.
     *
     * Сессии, кэш и очередь — состояние работающего процесса, а не данные
     * площадки: люди просто войдут заново. `migrations` заполняет migrate
     * на приёмнике, и копия поверх сделала бы список выполненных миграций
     * недостоверным.
     *
     * @var list<string>
     */
    private const SKIP = [
        'migrations',
        'sessions',
        'cache',
        'cache_locks',
        'jobs',
        'job_batches',
        'failed_jobs',
        'password_reset_tokens',
    ];

    /**
     * Таблицы, где строка ссылается на строку той же таблицы.
     * Значение — колонка самоссылки: по ней строится порядок вставки.
     *
     * @var array<string, string>
     */
    private const SELF_REFERENCING = [
        'categories' => 'parent_id',
    ];

    /**
     * Связи, разорванные при сортировке: таблица → список колонок,
     * которые вставляются пустыми и заполняются вторым проходом.
     *
     * @var array<string, list<string>>
     */
    private array $deferred = [];

    public function handle(): int
    {
        $from = DB::connection((string) $this->option('from'));
        $to = DB::connection((string) $this->option('to'));

        if ($from->getName() === $to->getName()) {
            $this->error('Источник и приёмник — одно подключение.');

            return self::FAILURE;
        }

        $tables = $this->tablesInDependencyOrder($from);

        if ($tables === []) {
            $this->error('В источнике нет таблиц. Сначала прогоните миграции.');

            return self::FAILURE;
        }

        $missing = array_values(array_diff($tables, $this->tableNames($to)));

        if ($missing !== []) {
            $this->error('В приёмнике нет таблиц: '.implode(', ', $missing));
            $this->line('Прогоните `php artisan migrate` на приёмнике до переноса.');

            return self::FAILURE;
        }

        $this->line('Источник: '.$from->getName().', приёмник: '.$to->getName());
        $this->line('Таблиц к переносу: '.count($tables));

        if ($this->deferred !== []) {
            foreach ($this->deferred as $table => $columns) {
                $this->line("Кольцевая связь разорвана: {$table}.".implode(', '.$table.'.', $columns));
            }
        }

        $this->newLine();

        if ($this->option('truncate')) {
            $this->truncate($to, $tables);
        }

        $report = [];

        foreach ($tables as $table) {
            try {
                $report[$table] = $this->copyTable($from, $to, $table);
            } catch (Throwable $e) {
                $this->newLine();
                $this->error("Таблица {$table}: ".$e->getMessage());

                return self::FAILURE;
            }
        }

        try {
            $this->fillDeferred($from, $to);
        } catch (Throwable $e) {
            $this->newLine();
            $this->error('Второй проход: '.$e->getMessage());

            return self::FAILURE;
        }

        $this->resetSequences($to, $tables);

        return $this->report($to, $report);
    }

    /**
     * Таблицы источника в порядке, пригодном для вставки.
     *
     * Побочный результат — `$this->deferred`: колонки, которые нельзя
     * заполнить сразу, потому что таблица, на которую они ссылаются,
     * вставляется позже.
     *
     * @return list<string>
     */
    private function tablesInDependencyOrder(ConnectionInterface $from): array
    {
        $all = array_values(array_filter(
            $this->tableNames($from),
            fn (string $name): bool => ! in_array($name, self::SKIP, true),
        ));

        /** @var array<string, array<string, string>> $edges таблица → [колонка → таблица, на которую ссылается] */
        $edges = [];

        foreach ($all as $table) {
            $edges[$table] = [];

            foreach (Schema::connection($from->getName())->getForeignKeys($table) as $key) {
                $column = $key['columns'][0] ?? null;
                $foreign = $key['foreign_table'];

                // Составные ключи вторым проходом не чинятся, самоссылка
                // решается сортировкой строк, ссылка на пропущенную
                // таблицу порядку не мешает
                if ($column === null || count($key['columns']) > 1) {
                    continue;
                }

                if ($foreign === $table || ! in_array($foreign, $all, true)) {
                    continue;
                }

                $edges[$table][$column] = $foreign;
            }
        }

        $ordered = [];
        $remaining = $edges;

        while ($remaining !== []) {
            $ready = array_keys(array_filter(
                $remaining,
                fn (array $deps): bool => array_diff(array_values($deps), $ordered) === [],
            ));

            if ($ready === []) {
                // Кольцо: берём таблицу с наименьшим числом незакрытых
                // связей, её ссылки вперёд заполним вторым проходом
                $ready = [$this->leastDependent($remaining, $ordered)];

                foreach ($remaining[$ready[0]] as $column => $foreign) {
                    if (! in_array($foreign, $ordered, true)) {
                        $this->deferred[$ready[0]][] = $column;
                    }
                }
            }

            foreach ($ready as $table) {
                $ordered[] = $table;
                unset($remaining[$table]);
            }
        }

        return $ordered;
    }

    /**
     * Таблица кольца с наименьшим числом незакрытых связей: чем меньше
     * колонок придётся обнулить, тем меньше работы второму проходу.
     *
     * @param  array<string, array<string, string>>  $remaining
     * @param  list<string>  $ordered
     */
    private function leastDependent(array $remaining, array $ordered): string
    {
        $unmet = array_map(
            fn (array $deps): int => count(array_diff(array_values($deps), $ordered)),
            $remaining,
        );

        asort($unmet);

        return (string) array_key_first($unmet);
    }

    /** @return list<string> */
    private function tableNames(ConnectionInterface $connection): array
    {
        return array_values(array_map(
            fn (array $table): string => $table['name'],
            Schema::connection($connection->getName())->getTables(),
        ));
    }

    /** @param list<string> $tables */
    private function truncate(ConnectionInterface $to, array $tables): void
    {
        $this->line('Очистка приёмника…');

        foreach (array_reverse($tables) as $table) {
            $to->table($table)->delete();
        }
    }

    /**
     * Копирование одной таблицы порциями.
     *
     * @return array{source: int, copied: int}
     */
    private function copyTable(ConnectionInterface $from, ConnectionInterface $to, string $table): array
    {
        $total = $from->table($table)->count();

        if ($total === 0) {
            $this->line("  {$table}: пусто");

            return ['source' => 0, 'copied' => 0];
        }

        $chunk = max(1, (int) $this->option('chunk'));
        $booleans = $this->booleanColumns($to, $table);
        $nulled = $this->deferred[$table] ?? [];
        $copied = 0;

        $bar = $this->output->createProgressBar($total);
        $bar->setFormat("  {$table}: %current%/%max%");
        $bar->start();

        foreach ($this->rows($from, $table, $chunk) as $rows) {
            $prepared = array_map(
                fn (array $row): array => $this->normalize($row, $booleans, $nulled),
                $rows,
            );

            $to->table($table)->insert($prepared);

            $copied += count($prepared);
            $bar->advance(count($prepared));
        }

        $bar->finish();
        $this->newLine();

        return ['source' => $total, 'copied' => $copied];
    }

    /**
     * Строки таблицы порциями, в порядке, пригодном для вставки.
     *
     * @return Generator<int, list<array<string, mixed>>>
     */
    private function rows(ConnectionInterface $from, string $table, int $chunk): Generator
    {
        $query = $from->table($table);

        if (isset(self::SELF_REFERENCING[$table])) {
            $sorted = $this->byDepth(
                $query->orderBy('id')->get()->map(fn (object $row): array => (array) $row)->all(),
                self::SELF_REFERENCING[$table],
            );

            foreach (array_chunk($sorted, $chunk) as $portion) {
                yield $portion;
            }

            return;
        }

        $buffer = [];

        foreach ($query->cursor() as $row) {
            $buffer[] = (array) $row;

            if (count($buffer) >= $chunk) {
                yield $buffer;
                $buffer = [];
            }
        }

        if ($buffer !== []) {
            yield $buffer;
        }
    }

    /**
     * Строки дерева в порядке от корней к листьям.
     *
     * Сортировки по самой колонке недостаточно: она даёт верный порядок
     * только пока id родителя меньше id ребёнка. Строка с родителем
     * id=200 и потомком id=30 в таком порядке приехала бы раньше своего
     * родителя и упёрлась во внешний ключ. Здесь у каждой строки
     * считается глубина — сколько шагов до корня, — и сортировка идёт
     * по ней.
     *
     * Битая ссылка (родителя нет) и кольцо считаются корнем: внешний
     * ключ такую строку всё равно не пропустит, и падение с понятным
     * сообщением лучше молчаливого зацикливания.
     *
     * @param  list<array<string, mixed>>  $rows
     * @return list<array<string, mixed>>
     */
    private function byDepth(array $rows, string $column): array
    {
        $parents = [];

        foreach ($rows as $row) {
            $parents[$row['id']] = $row[$column];
        }

        $depth = static function (mixed $id) use ($parents): int {
            $steps = 0;
            $seen = [];

            while ($id !== null && isset($parents[$id]) && $parents[$id] !== null) {
                if (isset($seen[$id])) {
                    return 0;
                }

                $seen[$id] = true;
                $id = $parents[$id];
                $steps++;
            }

            return $steps;
        };

        usort($rows, fn (array $a, array $b): int => [$depth($a['id']), $a['id']] <=> [$depth($b['id']), $b['id']]);

        return $rows;
    }

    /**
     * Булевы колонки приёмника: SQLite отдаёт 0 и 1, PostgreSQL требует
     * true и false.
     *
     * @return list<string>
     */
    private function booleanColumns(ConnectionInterface $to, string $table): array
    {
        return array_values(array_map(
            fn (array $column): string => $column['name'],
            array_filter(
                Schema::connection($to->getName())->getColumns($table),
                fn (array $column): bool => in_array($column['type_name'], ['bool', 'boolean'], true),
            ),
        ));
    }

    /**
     * @param  array<string, mixed>  $row
     * @param  list<string>  $booleans
     * @param  list<string>  $nulled
     * @return array<string, mixed>
     */
    private function normalize(array $row, array $booleans, array $nulled): array
    {
        foreach ($booleans as $column) {
            if (array_key_exists($column, $row) && $row[$column] !== null) {
                $row[$column] = (bool) $row[$column];
            }
        }

        foreach ($nulled as $column) {
            $row[$column] = null;
        }

        return $row;
    }

    /**
     * Второй проход: колонки, обнулённые ради разрыва кольца, заполняются
     * из источника — теперь строки, на которые они ссылаются, уже есть.
     */
    private function fillDeferred(ConnectionInterface $from, ConnectionInterface $to): void
    {
        if ($this->deferred === []) {
            return;
        }

        $this->newLine();
        $this->line('Второй проход: восстановление кольцевых связей…');

        foreach ($this->deferred as $table => $columns) {
            foreach ($columns as $column) {
                $filled = 0;

                $from->table($table)
                    ->select('id', $column)
                    ->whereNotNull($column)
                    ->orderBy('id')
                    ->chunk(500, function ($rows) use ($to, $table, $column, &$filled): void {
                        foreach ($rows as $row) {
                            $to->table($table)
                                ->where('id', $row->id)
                                ->update([$column => $row->{$column}]);

                            $filled++;
                        }
                    });

                $this->line("  {$table}.{$column}: {$filled}");
            }
        }
    }

    /**
     * Сброс счётчиков последовательностей приёмника.
     *
     * @param  list<string>  $tables
     */
    private function resetSequences(ConnectionInterface $to, array $tables): void
    {
        if ($to->getDriverName() !== 'pgsql') {
            return;
        }

        $this->newLine();
        $this->line('Сброс счётчиков последовательностей…');

        $reset = 0;

        foreach ($tables as $table) {
            $sequence = $to->scalar('select pg_get_serial_sequence(?, ?)', [$table, 'id']);

            if ($sequence === null) {
                continue;
            }

            // Третий аргумент false для пустой таблицы: иначе следующий
            // id стал бы двойкой и первая строка получила бы не первый номер
            $max = $to->scalar("select max(id) from {$table}");

            $to->statement('select setval(?, ?, ?)', [
                $sequence,
                $max === null ? 1 : (int) $max,
                $max !== null,
            ]);

            $reset++;
        }

        $this->line("  последовательностей обновлено: {$reset}");
    }

    /**
     * Сверка числа строк. Расхождение — отказ: молча переехавшая
     * наполовину база хуже, чем непереехавшая.
     *
     * @param  array<string, array{source: int, copied: int}>  $report
     */
    private function report(ConnectionInterface $to, array $report): int
    {
        $mismatched = [];

        foreach ($report as $table => $counts) {
            $target = $to->table($table)->count();

            if ($target !== $counts['source']) {
                $mismatched[] = [$table, $counts['source'], $target];
            }
        }

        $this->newLine();

        if ($mismatched !== []) {
            $this->error('Расхождение числа строк:');
            $this->table(['Таблица', 'Источник', 'Приёмник'], $mismatched);

            return self::FAILURE;
        }

        $rows = array_sum(array_column($report, 'copied'));
        $tables = count(array_filter($report, fn (array $c): bool => $c['copied'] > 0));

        $this->info("Перенесено строк: {$rows} в {$tables} таблицах. Число строк совпадает во всех таблицах.");

        return self::SUCCESS;
    }
}
