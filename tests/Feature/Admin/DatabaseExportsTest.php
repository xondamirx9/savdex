<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Jobs\RunDatabaseExport;
use App\Support\DatabaseExports;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Process\PendingProcess;
use Illuminate\Support\Carbon;
use Illuminate\Support\Facades\Process;
use Illuminate\Support\Facades\Queue;
use Illuminate\Support\Facades\Schema;
use Illuminate\Support\Facades\Storage;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Выгрузка базы в Excel по кнопке: очередь, выполнение, история.
 *
 * Раньше выгрузку делали командой в Shell на Render, файлы ложились
 * не на постоянный диск и пропадали при деплое. Теперь каждая выгрузка —
 * папка на постоянном диске с итогом в run.json.
 *
 * Обе версии выгружают, книги сверяются. Основная (чью книгу скачивают)
 * — Python; с EXPORTS_PRIMARY=php всё как до переключения. Python здесь
 * подменён — тестам PHP не нужен установленный Python, а все его исходы
 * проверяются явно.
 */
class DatabaseExportsTest extends TestCase
{
    use RefreshDatabase;

    private DatabaseExports $exports;

    protected function setUp(): void
    {
        parent::setUp();

        Storage::fake('local');
        $this->exports = app(DatabaseExports::class);

        // «Установленный» Python: любой существующий файл проходит
        // проверку наличия, сам запуск подменяет Process::fake
        // Основная версия задаётся в каждом разделе; по умолчанию здесь
        // — режим до переключения (PHP основная, Python в тени)
        config([
            'exports.primary' => 'php',
            'exports.python.enabled' => true,
            'exports.python.binary' => __FILE__,
        ]);
    }

    /**
     * Подменённый Python, который ещё и пишет книги в свой --dir —
     * как настоящий. Без этого отдавать в режиме «Python основная» нечего.
     */
    private function pythonWriting(string $stdout, int $exit = 0): void
    {
        Process::fake([
            '*' => function (PendingProcess $p) use ($stdout, $exit) {
                $dir = substr((string) collect($p->command)->first(fn ($a) => str_starts_with($a, '--dir=')), 6);

                foreach (['companies', 'listings'] as $book) {
                    file_put_contents("{$dir}/savdex-{$book}-2026-09-26-1200.xlsx", 'python');
                }

                return Process::result(output: $stdout, exitCode: $exit);
            },
        ]);
    }

    private function книга(array $run, string $file): string
    {
        return (string) Storage::disk('local')->get("exports/{$run['id']}/{$file}");
    }

    private function python(string $stdout, int $exit = 0, string $stderr = ''): void
    {
        Process::fake([
            '*' => Process::result(output: $stdout, errorOutput: $stderr, exitCode: $exit),
        ]);
    }

    private function итог(array $data): string
    {
        return "Записано…\nSAVDEX-RESULT ".json_encode($data, JSON_UNESCAPED_UNICODE)."\n";
    }

    private function runOnce(): array
    {
        $id = $this->exports->create(null);
        $this->exports->run($id);

        return $this->exports->find($id);
    }

    // ── Очередь ─────────────────────────────────────────────────────

    #[Test]
    public function кнопка_ставит_выгрузку_в_очередь(): void
    {
        Queue::fake();

        $id = $this->exports->queue(null);

        $this->assertSame(DatabaseExports::QUEUED, $this->exports->find($id)['status']);
        Queue::assertPushed(RunDatabaseExport::class, fn ($job) => $job->runId === $id);
    }

    #[Test]
    public function вторая_выгрузка_не_запускается_пока_идёт_первая(): void
    {
        Queue::fake();

        $this->assertNotNull($this->exports->queue(null));
        $this->assertNull($this->exports->queue(null));

        Queue::assertPushed(RunDatabaseExport::class, 1);
    }

    #[Test]
    public function зависшая_выгрузка_не_блокирует_кнопку_навсегда(): void
    {
        Queue::fake();

        $id = $this->exports->queue(null);

        // Воркер умер посреди работы — через полчаса она прервана
        Carbon::setTestNow(now()->addMinutes(31));

        $this->assertSame(DatabaseExports::FAILED, $this->exports->find($id) ? $this->exports->all()[0]['status'] : null);
        $this->assertNotNull($this->exports->queue(null));
    }

    // ── Выполнение ──────────────────────────────────────────────────

    #[Test]
    public function выгрузка_кладёт_книги_на_постоянный_диск(): void
    {
        config(['exports.python.enabled' => false]);

        $run = $this->runOnce();

        $this->assertSame(DatabaseExports::DONE, $run['status']);
        $this->assertTrue($run['php']['ok']);
        $this->assertCount(2, $run['php']['files']);

        foreach ($run['php']['files'] as $file) {
            Storage::disk('local')->assertExists("exports/{$run['id']}/{$file}");
        }

        $this->assertSame('skipped', $run['python']['status']);
    }

    #[Test]
    public function python_совпал(): void
    {
        $this->python($this->итог(['self_check' => true, 'compared' => true, 'differences' => 0, 'problems' => []]));

        $run = $this->runOnce();

        $this->assertSame('match', $run['python']['status']);

        // Python получает адрес той же базы и папку PHP-книг для сверки
        Process::assertRan(fn (PendingProcess $p) => in_array('--json', $p->command, true)
            && in_array('--compare-with='.$this->exports->path($run['id']), $p->command, true)
            && isset($p->environment['DATABASE_URL']));
    }

    #[Test]
    public function python_расходится(): void
    {
        $this->python($this->итог([
            'self_check' => true, 'compared' => true, 'differences' => 2,
            'problems' => ['Объявления!V3: PHP …, Python …'],
        ]), exit: 1);

        $run = $this->runOnce();

        $this->assertSame(DatabaseExports::DONE, $run['status'], 'Сбой тени не должен ронять выгрузку');
        $this->assertSame('differs', $run['python']['status']);
        $this->assertSame(2, $run['python']['differences']);
        $this->assertSame(['Объявления!V3: PHP …, Python …'], $run['python']['problems']);
    }

    #[Test]
    public function собственная_сверка_python_не_сошлась(): void
    {
        $this->python($this->итог([
            'self_check' => false, 'self_problems' => ['Компании: строк в базе 3, в файле 2'],
            'compared' => true, 'differences' => 0,
        ]), exit: 1);

        $this->assertSame('differs', $this->runOnce()['python']['status']);
    }

    #[Test]
    public function python_упал_выгрузка_всё_равно_готова(): void
    {
        $this->python('', exit: 1, stderr: 'ValueError: Unable to configure root logger');

        $run = $this->runOnce();

        $this->assertSame(DatabaseExports::DONE, $run['status']);
        $this->assertSame('failed', $run['python']['status']);
        $this->assertStringContainsString('Unable to configure root logger', $run['python']['note']);
    }

    #[Test]
    public function python_не_установлен(): void
    {
        config(['exports.python.binary' => '/нет/такого/python']);

        $run = $this->runOnce();

        $this->assertSame(DatabaseExports::DONE, $run['status']);
        $this->assertSame('skipped', $run['python']['status']);
        $this->assertStringContainsString('Python не установлен', $run['python']['note']);
    }

    #[Test]
    public function сбой_php_выгрузки_честно_отмечен(): void
    {
        // Описание листа врёт о таблице — выгрузка обязана отказать
        Schema::drop('favorites');
        config(['exports.python.enabled' => false]);

        $run = $this->runOnce();

        $this->assertSame(DatabaseExports::FAILED, $run['status']);
        $this->assertFalse($run['php']['ok']);
        $this->assertSame('skipped', $run['python']['status']);
    }

    #[Test]
    public function умершая_задача_отмечает_выгрузку_упавшей(): void
    {
        Queue::fake();
        $id = $this->exports->queue(null);

        (new RunDatabaseExport($id))->failed(new \RuntimeException('воркер убит'));

        $this->assertSame(DatabaseExports::FAILED, $this->exports->find($id)['status']);
        $this->assertNull($this->exports->active());
    }

    // ── Python — основная версия ────────────────────────────────────

    #[Test]
    public function по_умолчанию_основная_python(): void
    {
        // setUp переставил режим — смотрим сам файл настроек
        $this->assertSame('python', (require config_path('exports.php'))['primary']);

        config(['exports.primary' => 'python']);
        $this->assertSame('python', $this->exports->primary());

        // Python выключен совсем — основной быть не может
        config(['exports.python.enabled' => false]);
        $this->assertSame('php', $this->exports->primary());
    }

    #[Test]
    public function python_основная_отдаёт_свои_книги(): void
    {
        config(['exports.primary' => 'python']);
        $this->pythonWriting($this->итог(['self_check' => true, 'compared' => true, 'differences' => 0, 'problems' => []]));

        $run = $this->runOnce();

        $this->assertSame(DatabaseExports::DONE, $run['status']);
        $this->assertSame('python', $run['engine']);
        $this->assertSame('match', $run['python']['status']);
        $this->assertCount(2, $run['files']);

        foreach ($run['files'] as $file) {
            $this->assertSame('python', $this->книга($run, $file));
            $this->assertNotNull($this->exports->bookPath($run['id'], $file));
        }

        // PHP-книги — рядом, в php/, и с ними Python сверялся
        $this->assertCount(2, Storage::disk('local')->files("exports/{$run['id']}/php"));
        Process::assertRan(fn (PendingProcess $p) => in_array('--compare-with='.$this->exports->path($run['id']).'/php', $p->command, true)
            && in_array('--dir='.$this->exports->path($run['id']), $p->command, true));
    }

    #[Test]
    public function python_сошёлся_с_базой_но_расходится_с_php(): void
    {
        // Книга Python верна базе — её и отдают, а расхождение видно в итоге
        config(['exports.primary' => 'python']);
        $this->pythonWriting($this->итог([
            'self_check' => true, 'compared' => true, 'differences' => 1,
            'problems' => ['Тендеры!T21: PHP …, Python …'],
        ]), exit: 1);

        $run = $this->runOnce();

        $this->assertSame('python', $run['engine']);
        $this->assertSame('differs', $run['python']['status']);
        $this->assertSame(['Тендеры!T21: PHP …, Python …'], $run['python']['problems']);
    }

    #[Test]
    public function python_не_сошёлся_с_базой_отдаются_книги_php(): void
    {
        config(['exports.primary' => 'python']);
        $this->pythonWriting($this->итог([
            'self_check' => false, 'self_problems' => ['Компании: строк в базе 3, в файле 2'],
            'compared' => true, 'differences' => 0,
        ]), exit: 1);

        $run = $this->runOnce();

        $this->assertSame(DatabaseExports::DONE, $run['status']);
        $this->assertSame('php', $run['engine']);
        $this->assertSame('differs', $run['python']['status']);
        $this->assertStringContainsString('отданы книги PHP-версии', $run['note']);
        $this->assertCount(2, $run['files']);

        // Несошедшиеся Python-книги убраны, на их месте — PHP-книги
        foreach ($run['files'] as $file) {
            $this->assertNotSame('python', $this->книга($run, $file));
        }

        $this->assertCount(3, Storage::disk('local')->files("exports/{$run['id']}"), 'две книги и run.json');
    }

    #[Test]
    public function python_упал_отдаются_книги_php(): void
    {
        config(['exports.primary' => 'python']);
        $this->python('', exit: 1, stderr: 'psycopg.OperationalError: connection refused');

        $run = $this->runOnce();

        $this->assertSame(DatabaseExports::DONE, $run['status']);
        $this->assertSame('php', $run['engine']);
        $this->assertSame('failed', $run['python']['status']);
        $this->assertStringContainsString('connection refused', $run['python']['note']);
        $this->assertCount(2, $run['files']);

        foreach ($run['files'] as $file) {
            $this->assertNotNull($this->exports->bookPath($run['id'], $file));
        }
    }

    #[Test]
    public function python_не_установлен_отдаются_книги_php(): void
    {
        config(['exports.primary' => 'python', 'exports.python.binary' => '/нет/такого/python']);

        $run = $this->runOnce();

        $this->assertSame(DatabaseExports::DONE, $run['status']);
        $this->assertSame('php', $run['engine']);
        $this->assertSame('skipped', $run['python']['status']);
        $this->assertCount(2, $run['files']);
    }

    #[Test]
    public function php_упала_python_всё_равно_отдаёт_книги(): void
    {
        Schema::drop('favorites');
        config(['exports.primary' => 'python']);
        $this->pythonWriting($this->итог(['self_check' => true, 'compared' => false, 'differences' => 0, 'problems' => []]));

        $run = $this->runOnce();

        $this->assertSame(DatabaseExports::DONE, $run['status']);
        $this->assertSame('python', $run['engine']);
        $this->assertFalse($run['php']['ok']);
        $this->assertSame('skipped', $run['python']['status']);

        // Сверять не с чем — и Python не просят
        Process::assertRan(fn (PendingProcess $p) => collect($p->command)->every(fn ($a) => ! str_starts_with($a, '--compare-with')));
    }

    #[Test]
    public function не_удались_обе_версии(): void
    {
        Schema::drop('favorites');
        config(['exports.primary' => 'python']);
        $this->python('', exit: 1, stderr: 'boom');

        $run = $this->runOnce();

        $this->assertSame(DatabaseExports::FAILED, $run['status']);
        $this->assertSame('не удались обе версии выгрузки', $run['note']);
        $this->assertArrayNotHasKey('files', $run);
    }

    #[Test]
    public function сбой_в_команде_не_оставляет_выгрузку_идущей(): void
    {
        // База недоступна: выгрузка падает целиком, а кнопка не должна
        // быть заблокирована полчаса
        $this->mock(DatabaseExports::class, function ($mock) {
            $mock->makePartial();
            $mock->shouldReceive('run')->andThrow(new \RuntimeException('connection refused'));
        });

        try {
            $this->artisan('savdex:export-run')->run();
            $this->fail('исключение должно дойти до консоли');
        } catch (\RuntimeException) {
        }

        $exports = app(DatabaseExports::class);
        $this->assertNull($exports->active());
        $this->assertSame(DatabaseExports::FAILED, $exports->all()[0]['status']);
        $this->assertSame('connection refused', $exports->all()[0]['note']);
    }

    #[Test]
    public function команда_называет_версию_отдавшую_книги(): void
    {
        config(['exports.primary' => 'python']);
        $this->pythonWriting($this->итог(['self_check' => true, 'compared' => true, 'differences' => 0, 'problems' => []]));

        $this->artisan('savdex:export-run')
            ->expectsOutputToContain('Книги отдала версия: python')
            ->expectsOutputToContain('Сверка с Python: match')
            ->assertSuccessful();
    }

    // ── История и файлы ─────────────────────────────────────────────

    #[Test]
    public function хранятся_последние_десять(): void
    {
        config(['exports.python.enabled' => false, 'exports.keep' => 3]);

        foreach (range(1, 5) as $i) {
            Carbon::setTestNow(now()->addMinute());
            $this->runOnce();
        }

        $this->assertCount(3, $this->exports->all());
    }

    #[Test]
    public function скачать_можно_только_книгу_выгрузки(): void
    {
        config(['exports.python.enabled' => false]);
        $run = $this->runOnce();
        $book = $run['php']['files'][0];

        $this->assertNotNull($this->exports->bookPath($run['id'], $book));

        // Никаких «..», служебных и чужих файлов
        $this->assertNull($this->exports->bookPath($run['id'], 'run.json'));
        $this->assertNull($this->exports->bookPath($run['id'], '../../.env'));
        $this->assertNull($this->exports->bookPath('../'.$run['id'], $book));
        $this->assertNull($this->exports->bookPath($run['id'], 'python/'.$book));
    }

    // ── Адрес базы для Python ───────────────────────────────────────

    #[Test]
    public function адрес_базы_берётся_из_действующих_настроек(): void
    {
        config([
            'database.default' => 'pgsql',
            'database.connections.pgsql.url' => null,
            'database.connections.pgsql.host' => 'db.internal',
            'database.connections.pgsql.port' => '5432',
            'database.connections.pgsql.database' => 'savdex',
            'database.connections.pgsql.username' => 'savdex',
            'database.connections.pgsql.password' => 'p@ss/word',
        ]);

        // Пароль с «@» и «/» не ломает адрес
        $this->assertSame('postgres://savdex:p%40ss%2Fword@db.internal:5432/savdex', $this->exports->databaseUrl());

        config(['database.connections.pgsql.url' => 'postgresql://u:p@render-db/savdex']);
        $this->assertSame('postgresql://u:p@render-db/savdex', $this->exports->databaseUrl());

        config(['database.default' => 'sqlite', 'database.connections.sqlite.database' => '/var/data/database.sqlite']);
        $this->assertSame('sqlite:////var/data/database.sqlite', $this->exports->databaseUrl());
    }

    // ── Консоль ─────────────────────────────────────────────────────

    #[Test]
    public function команда_выгружает_сразу_без_очереди(): void
    {
        Queue::fake();
        config(['exports.python.enabled' => false]);

        $this->artisan('savdex:export-run')
            ->expectsOutputToContain('Итог: done')
            ->assertSuccessful();

        // Задача в очереди выполнила бы выгрузку второй раз
        Queue::assertNothingPushed();
    }
}
