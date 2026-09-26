<?php

declare(strict_types=1);

namespace App\Support;

use App\Jobs\RunDatabaseExport;
use App\Models\User;
use Illuminate\Contracts\Filesystem\Filesystem;
use Illuminate\Database\ConnectionInterface;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Artisan;
use Illuminate\Support\Facades\DB;
use Illuminate\Support\Facades\Process;
use Illuminate\Support\Facades\Storage;
use Illuminate\Support\Str;
use Symfony\Component\Process\Exception\ProcessTimedOutException;
use Throwable;

/**
 * Выгрузки базы в Excel, запускаемые из админки.
 *
 * Раньше выгрузку можно было сделать только командой в Shell на Render,
 * а файлы ложились в storage/app/exports — не на постоянный диск — и
 * пропадали при следующем деплое. Скачать их из Shell было нельзя. Теперь
 * каждая выгрузка — папка на постоянном диске:
 *
 *   exports/2026-09-26-125530-ab12/
 *     run.json                          — кто, когда, чем кончилось
 *     savdex-companies-….xlsx           — книги основной версии: их и скачивают
 *     savdex-listings-….xlsx
 *     php/savdex-….xlsx                 — книги PHP-версии, для сверки
 *
 * Выгрузку делают обе версии из одного снимка базы, и книги сверяются
 * ячейка в ячейку. Основная — Python (config/exports.php, primary): после
 * пяти совпадений подряд на боевом сервере скачиваемым файлом стала его
 * книга, а PHP-версия ушла в тень, чтобы расхождение по-прежнему было
 * видно. Если Python-выгрузка не удалась, отдаётся файл PHP-версии —
 * выгрузка из-за переезда не пропадает.
 *
 * С primary=php всё как до переключения: скачивается PHP-файл, книги
 * Python лежат в python/. Старые выгрузки в истории устроены так же.
 */
class DatabaseExports
{
    public const QUEUED = 'queued';

    public const RUNNING = 'running';

    public const DONE = 'done';

    public const FAILED = 'failed';

    /** Метка строки итога в выводе Python-команды (см. export_xlsx.py) */
    private const RESULT = 'SAVDEX-RESULT ';

    /** Номер выгрузки: время и хвост от совпадения в одну секунду */
    private const ID = '/^\d{4}-\d{2}-\d{2}-\d{6}-[a-z0-9]{4}$/';

    /** Имя книги, которую можно скачать */
    private const BOOK = '/^savdex-(companies|listings)-[0-9-]+\.xlsx$/';

    private function disk(): Filesystem
    {
        return Storage::disk('local');
    }

    private function root(): string
    {
        return (string) config('exports.directory', 'exports');
    }

    // ── Очередь ─────────────────────────────────────────────────────

    /**
     * Поставить выгрузку в очередь. null — одна уже идёт.
     *
     * Две сразу не запускаются: выгрузка читает всю базу, и вторая
     * параллельная удваивает нагрузку ради того же самого файла.
     */
    public function queue(?User $user): ?string
    {
        $id = $this->create($user);

        if ($id !== null) {
            RunDatabaseExport::dispatch($id);
        }

        return $id;
    }

    /**
     * Завести выгрузку, не ставя в очередь. null — одна уже идёт.
     *
     * Отдельно от queue() для консоли: там выгрузка выполняется сразу,
     * и задача в очереди выполнила бы её второй раз.
     */
    public function create(?User $user): ?string
    {
        if ($this->active() !== null) {
            return null;
        }

        $id = now()->format('Y-m-d-His').'-'.Str::lower(Str::random(4));

        $this->save($id, [
            'id' => $id,
            'status' => self::QUEUED,
            'requested_by' => $user?->name ?? 'консоль',
            'requested_by_id' => $user?->getKey(),
            'queued_at' => now()->toIso8601String(),
        ]);

        return $id;
    }

    /** Идущая или ждущая выгрузка, если есть. */
    public function active(): ?array
    {
        foreach ($this->all() as $run) {
            if (in_array($run['status'], [self::QUEUED, self::RUNNING], true)) {
                return $run;
            }
        }

        return null;
    }

    // ── Выполнение ──────────────────────────────────────────────────

    public function run(string $id): void
    {
        $run = $this->find($id);

        if ($run === null) {
            return;
        }

        $this->update($id, ['status' => self::RUNNING, 'started_at' => now()->toIso8601String()]);

        $dir = $this->path($id);
        $db = DB::connection();
        $snapshot = $this->openSnapshot($db);

        try {
            $this->export($id, $dir, $snapshot);
        } finally {
            if ($snapshot !== null) {
                // Транзакция только читала. Закрыть её обязательно:
                // обработчик очереди потом удаляет задачу через это же
                // подключение, а внутри READ ONLY это не удалось бы
                $db->rollBack();
            }
        }

        $this->prune();
    }

    /** Какая версия делает скачиваемые книги. */
    public function primary(): string
    {
        return config('exports.primary') === 'python' && config('exports.python.enabled') ? 'python' : 'php';
    }

    /** Обе версии — из одного снимка базы; основная определяет, что скачивают. */
    private function export(string $id, string $dir, ?string $snapshot): void
    {
        if ($this->primary() === 'python') {
            $this->exportByPython($id, $dir, $snapshot);
        } else {
            $this->exportByPhp($id, $dir, $snapshot);
        }
    }

    /**
     * Основная — Python, PHP-версия в тени для сверки.
     *
     * Сначала PHP-книги в php/, затем Python пишет свои на место
     * скачиваемых и сверяет их с PHP-книгами. Python-книга отдаётся,
     * только если сошлась с базой (собственная сверка): расхождение
     * с PHP при этом видно в итоге, как раньше было видно расхождение
     * Python с PHP. Не удалась Python-выгрузка — отдаются PHP-книги.
     */
    private function exportByPython(string $id, string $dir, ?string $snapshot): void
    {
        $php = $this->runPhp($dir.'/php');
        $this->update($id, ['engine' => 'python', 'php' => $php]);

        try {
            $python = $this->runPython($dir, $php['ok'] ? $dir.'/php' : null, $snapshot);
        } catch (Throwable $e) {
            report($e);
            $python = ['status' => 'failed', 'note' => mb_substr($e->getMessage(), 0, 300)];
        }

        $usable = ($python['self_check'] ?? false) && count($this->books($id)) === 2;

        if ($usable) {
            $this->update($id, [
                'status' => self::DONE,
                'engine' => 'python',
                'files' => $this->books($id),
                'python' => $python,
                'finished_at' => now()->toIso8601String(),
            ]);

            return;
        }

        // Python не справился: его недописанные или несошедшиеся книги
        // не отдаются, на их место встают PHP-книги
        foreach ($this->books($id) as $file) {
            $this->disk()->delete($this->root()."/{$id}/{$file}");
        }

        if (! $php['ok']) {
            $this->update($id, [
                'status' => self::FAILED,
                'python' => $python,
                'note' => 'не удались обе версии выгрузки',
                'finished_at' => now()->toIso8601String(),
            ]);

            return;
        }

        foreach ($this->books($id, 'php') as $file) {
            $this->disk()->move($this->root()."/{$id}/php/{$file}", $this->root()."/{$id}/{$file}");
        }

        $this->update($id, [
            'status' => self::DONE,
            'engine' => 'php',
            'files' => $this->books($id),
            'python' => $python,
            'note' => 'Python-выгрузка не удалась — отданы книги PHP-версии',
            'finished_at' => now()->toIso8601String(),
        ]);
    }

    /**
     * Основная — PHP, Python в тени (как до переключения).
     */
    private function exportByPhp(string $id, string $dir, ?string $snapshot): void
    {
        $php = $this->runPhp($dir);
        $php['files'] = $this->books($id);

        if (! $php['ok']) {
            $this->update($id, [
                'status' => self::FAILED,
                'engine' => 'php',
                'php' => $php,
                'python' => ['status' => 'skipped', 'note' => 'PHP-выгрузка не удалась — сверять не с чем'],
                'finished_at' => now()->toIso8601String(),
            ]);

            return;
        }

        $this->update($id, ['engine' => 'php', 'files' => $php['files'], 'php' => $php]);

        // Тень: сбой Python не должен ронять выгрузку, файлы уже готовы
        try {
            $python = $this->shadowPython($dir, $snapshot);
        } catch (Throwable $e) {
            report($e);
            $python = ['status' => 'failed', 'note' => mb_substr($e->getMessage(), 0, 300)];
        }

        $this->update($id, [
            'status' => self::DONE,
            'python' => $python,
            'finished_at' => now()->toIso8601String(),
        ]);
    }

    /**
     * PHP-выгрузка в каталог. Внутри открытого снимка она его и читает.
     *
     * @return array{ok: bool, output: string}
     */
    private function runPhp(string $dir): array
    {
        try {
            $code = Artisan::call('savdex:export-xlsx', ['--dir' => $dir]);
            $output = Artisan::output();
        } catch (Throwable $e) {
            report($e);
            $code = 1;
            $output = $e->getMessage();
        }

        return ['ok' => $code === 0, 'output' => self::tail($output)];
    }

    /**
     * Открыть снимок базы, общий для PHP- и Python-выгрузки.
     *
     * Сайт живёт, пока идёт выгрузка: счётчики просмотров растут между
     * чтением PHP-версии и чтением Python-версии, и исправные книги
     * «расходились» на один просмотр (на боевом сервере — две сверки
     * из пяти). PostgreSQL умеет отдать снимок своей транзакции другому
     * процессу: pg_export_snapshot() здесь, SET TRANSACTION SNAPSHOT
     * в Python-версии. Снимок живёт, пока открыта эта транзакция, —
     * поэтому она закрывается только после сверки на Python.
     *
     * Не PostgreSQL (SQLite в тестах) — снимка нет, всё как раньше.
     */
    private function openSnapshot(ConnectionInterface $db): ?string
    {
        if ($db->getDriverName() !== 'pgsql' || $db->transactionLevel() > 0) {
            return null;
        }

        $db->beginTransaction();

        try {
            $db->statement('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY');

            return (string) $db->scalar('select pg_export_snapshot()');
        } catch (Throwable $e) {
            $db->rollBack();

            throw $e;
        }
    }

    /** Отметить выгрузку упавшей — когда задача очереди умерла целиком. */
    public function markFailed(string $id, string $reason): void
    {
        if ($this->find($id) === null) {
            return;
        }

        $this->update($id, [
            'status' => self::FAILED,
            'note' => mb_substr($reason, 0, 300),
            'finished_at' => now()->toIso8601String(),
        ]);
    }

    /**
     * Python-версия в тени: выгружает те же данные в python/ и сверяет
     * свои книги с PHP-книгами.
     *
     * @return array<string, mixed>
     */
    private function shadowPython(string $dir, ?string $snapshot): array
    {
        return $this->runPython($dir.'/python', $dir, $snapshot);
    }

    /**
     * Python-выгрузка в каталог, со сверкой с PHP-книгами, если они есть.
     *
     * status: match — обе сверки сошлись; differs — не сошлась собственная
     * сверка или книги расходятся с PHP; skipped — не с чем сверять или
     * Python не установлен; failed / timeout — Python не справился.
     * self_check — сошлась ли Python-книга с базой: только такую можно
     * отдавать.
     *
     * @return array<string, mixed>
     */
    private function runPython(string $dir, ?string $compareWith, ?string $snapshot): array
    {
        if (! config('exports.python.enabled')) {
            return ['status' => 'skipped', 'note' => 'сверка с Python выключена (EXPORTS_PYTHON_SHADOW)'];
        }

        $binary = (string) config('exports.python.binary');

        if (! is_file($binary)) {
            return ['status' => 'skipped', 'note' => "Python не установлен: нет {$binary}"];
        }

        try {
            $result = Process::path(base_path('python'))
                ->timeout((int) config('exports.python.timeout', 300))
                ->env([
                    'DATABASE_URL' => $this->databaseUrl(),
                    'PYTHONDONTWRITEBYTECODE' => '1',
                ])
                ->run([
                    $binary, 'manage.py', 'export_xlsx',
                    '--dir='.$dir,
                    ...($compareWith !== null ? ['--compare-with='.$compareWith] : []),
                    '--json',
                    ...($snapshot !== null ? ['--snapshot='.$snapshot] : []),
                ]);
        } catch (ProcessTimedOutException) {
            return ['status' => 'timeout', 'note' => 'Python-выгрузка не уложилась в '.config('exports.python.timeout').' с'];
        }

        $line = collect(explode("\n", $result->output()))
            ->first(fn (string $l): bool => str_starts_with($l, self::RESULT));

        if ($line === null) {
            return [
                'status' => 'failed',
                'note' => self::tail($result->errorOutput() ?: $result->output()),
            ];
        }

        $data = json_decode(substr($line, strlen(self::RESULT)), true) ?: [];
        $differences = (int) ($data['differences'] ?? 0);
        $selfCheck = (bool) ($data['self_check'] ?? false);
        $problems = array_slice([...($data['self_problems'] ?? []), ...($data['problems'] ?? [])], 0, 20);

        if ($selfCheck && $compareWith === null) {
            return [
                'status' => 'skipped',
                'self_check' => true,
                'note' => 'PHP-выгрузка не удалась — сверять не с чем',
            ];
        }

        return [
            'status' => $differences === 0 && $selfCheck ? 'match' : 'differs',
            'self_check' => $selfCheck,
            'differences' => $differences,
            'problems' => $problems,
        ];
    }

    /**
     * Адрес базы для Python — из действующих настроек Laravel.
     *
     * Не из переменных окружения: переменные базы на Render заданы
     * в панели, а не в render.yaml, и гадать по файлу нельзя. Так обе
     * версии гарантированно выгружают из одной и той же базы.
     */
    public function databaseUrl(): string
    {
        $name = (string) config('database.default');
        $c = (array) config("database.connections.{$name}");

        if (($c['driver'] ?? '') === 'sqlite') {
            return 'sqlite:///'.$c['database'];
        }

        if (! empty($c['url'])) {
            return (string) $c['url'];
        }

        return sprintf(
            'postgres://%s:%s@%s:%s/%s',
            rawurlencode((string) ($c['username'] ?? '')),
            rawurlencode((string) ($c['password'] ?? '')),
            $c['host'] ?? '127.0.0.1',
            $c['port'] ?? '5432',
            $c['database'] ?? '',
        );
    }

    // ── История ─────────────────────────────────────────────────────

    /**
     * Все выгрузки, новые сверху.
     *
     * Зависшая дольше stale_minutes считается прерванной: воркер мог
     * умереть посреди работы, и без этого кнопка осталась бы
     * заблокированной навсегда.
     *
     * @return list<array<string, mixed>>
     */
    public function all(): array
    {
        $runs = [];

        foreach ($this->disk()->directories($this->root()) as $path) {
            $run = $this->find(basename($path));

            if ($run !== null) {
                $runs[] = $this->withStaleness($run);
            }
        }

        usort($runs, fn (array $a, array $b): int => strcmp($b['id'], $a['id']));

        return $runs;
    }

    public function find(string $id): ?array
    {
        if (preg_match(self::ID, $id) !== 1) {
            return null;
        }

        $json = $this->disk()->get($this->root()."/{$id}/run.json");

        return is_string($json) ? (json_decode($json, true) ?: null) : null;
    }

    /** @param array<string, mixed> $run */
    private function withStaleness(array $run): array
    {
        if (! in_array($run['status'], [self::QUEUED, self::RUNNING], true)) {
            return $run;
        }

        $since = Carbon::parse($run['started_at'] ?? $run['queued_at']);

        if ($since->diffInMinutes(now()) >= (int) config('exports.stale_minutes', 30)) {
            $run['status'] = self::FAILED;
            $run['note'] = 'прервана: не закончилась за '.config('exports.stale_minutes').' минут';
        }

        return $run;
    }

    /**
     * Путь к книге для скачивания, только если она настоящая.
     *
     * Номер выгрузки и имя файла приходят из адреса — никакого `..`
     * и чужих файлов: оба сверяются с жёстким шаблоном.
     */
    public function bookPath(string $id, string $file): ?string
    {
        if (preg_match(self::ID, $id) !== 1 || preg_match(self::BOOK, $file) !== 1) {
            return null;
        }

        $path = $this->root()."/{$id}/{$file}";

        return $this->disk()->exists($path) ? $path : null;
    }

    /** @return list<string> */
    private function books(string $id, string $subdir = ''): array
    {
        return collect($this->disk()->files($this->root()."/{$id}".($subdir !== '' ? "/{$subdir}" : '')))
            ->map(fn (string $p): string => basename($p))
            ->filter(fn (string $name): bool => preg_match(self::BOOK, $name) === 1)
            ->sort()
            ->values()
            ->all();
    }

    /** Хранятся последние keep выгрузок; идущие не трогаются. */
    private function prune(): void
    {
        $keep = max(1, (int) config('exports.keep', 10));

        foreach (array_slice($this->all(), $keep) as $run) {
            if (in_array($run['status'], [self::QUEUED, self::RUNNING], true)) {
                continue;
            }

            $this->disk()->deleteDirectory($this->root().'/'.$run['id']);
        }
    }

    // ── Файлы ───────────────────────────────────────────────────────

    public function path(string $id): string
    {
        return $this->disk()->path($this->root()."/{$id}");
    }

    /** @param array<string, mixed> $run */
    private function save(string $id, array $run): void
    {
        $this->disk()->makeDirectory($this->root()."/{$id}");
        $this->disk()->put(
            $this->root()."/{$id}/run.json",
            json_encode($run, JSON_UNESCAPED_UNICODE | JSON_PRETTY_PRINT),
        );
    }

    /** @param array<string, mixed> $changes */
    private function update(string $id, array $changes): void
    {
        $this->save($id, array_merge($this->find($id) ?? ['id' => $id], $changes));
    }

    private static function tail(string $text): string
    {
        return mb_substr(trim($text), -2000);
    }
}
