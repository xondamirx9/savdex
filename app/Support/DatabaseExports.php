<?php

declare(strict_types=1);

namespace App\Support;

use App\Jobs\RunDatabaseExport;
use App\Models\User;
use Illuminate\Contracts\Filesystem\Filesystem;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Artisan;
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
 *     savdex-companies-….xlsx           — книги PHP-версии: их и скачивают
 *     savdex-listings-….xlsx
 *     python/savdex-….xlsx              — книги Python-версии, для сверки
 *
 * Python-версия работает в тени (см. config/exports.php): её сбой
 * отмечается в итоге, но выгрузку не роняет — скачивается PHP-файл.
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

        try {
            $code = Artisan::call('savdex:export-xlsx', ['--dir' => $dir]);
            $output = Artisan::output();
        } catch (Throwable $e) {
            report($e);
            $code = 1;
            $output = $e->getMessage();
        }

        $php = [
            'ok' => $code === 0,
            'output' => self::tail($output),
            'files' => $this->books($id),
        ];

        if (! $php['ok']) {
            $this->update($id, [
                'status' => self::FAILED,
                'php' => $php,
                'python' => ['status' => 'skipped', 'note' => 'PHP-выгрузка не удалась — сверять не с чем'],
                'finished_at' => now()->toIso8601String(),
            ]);

            return;
        }

        $this->update($id, ['php' => $php]);

        // Тень: сбой Python не должен ронять выгрузку, файлы уже готовы
        try {
            $python = $this->shadow($dir);
        } catch (Throwable $e) {
            report($e);
            $python = ['status' => 'failed', 'note' => mb_substr($e->getMessage(), 0, 300)];
        }

        $this->update($id, [
            'status' => self::DONE,
            'python' => $python,
            'finished_at' => now()->toIso8601String(),
        ]);

        $this->prune();
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
     * Python-версия выгружает те же данные рядом и сверяет книги.
     *
     * @return array{status: string, note?: string, differences?: int, problems?: list<string>}
     */
    private function shadow(string $dir): array
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
                    '--dir='.$dir.'/python',
                    '--compare-with='.$dir,
                    '--json',
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

        return [
            'status' => $differences === 0 && $selfCheck ? 'match' : 'differs',
            'differences' => $differences,
            'problems' => array_slice([...($data['self_problems'] ?? []), ...($data['problems'] ?? [])], 0, 20),
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
    private function books(string $id): array
    {
        return collect($this->disk()->files($this->root()."/{$id}"))
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
