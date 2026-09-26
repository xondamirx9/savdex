<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Filament\Pages\ExcelExports;
use App\Jobs\RunDatabaseExport;
use App\Models\AdminAction;
use App\Models\User;
use App\Support\AdminAccess;
use App\Support\DatabaseExports;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\Queue;
use Illuminate\Support\Facades\Storage;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Страница «Выгрузка в Excel» в админке.
 *
 * В файлах почта, телефоны и IP всех пользователей разом, поэтому
 * доступ — отдельный раздел, которого нет ни в одной роли: только
 * суперадмину и тем, кому выдан поимённо. Запуск и каждое скачивание —
 * в журнале действий.
 */
class ExcelExportsPageTest extends TestCase
{
    use RefreshDatabase;

    protected function setUp(): void
    {
        parent::setUp();

        Storage::fake('local');
        config(['exports.python.enabled' => false]);
    }

    private function admin(string $role, array $grant = []): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => $role,
            'status' => 'active',
            'admin_permissions' => $grant === [] ? null : ['grant' => $grant],
        ]);
    }

    private function finishedRun(): array
    {
        $exports = app(DatabaseExports::class);
        $id = $exports->create(null);
        $exports->run($id);

        return $exports->find($id);
    }

    // ── Доступ ──────────────────────────────────────────────────────

    #[Test]
    public function суперадмин_видит_страницу(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPERADMIN))
            ->get('/admin/excel-exports')
            ->assertOk()
            ->assertSee('Выгрузка в Excel');
    }

    #[Test]
    public function администратор_без_права_не_видит(): void
    {
        /*
         * Даже у администратора — у которого есть «выгрузить компании» —
         * права на всю базу нет: это шире, чем любой отдельный раздел.
         */
        $this->actingAs($this->admin(AdminAccess::ADMIN))
            ->get('/admin/excel-exports')
            ->assertForbidden();
    }

    #[Test]
    public function выданное_поимённо_право_открывает_страницу(): void
    {
        $this->actingAs($this->admin(AdminAccess::ADMIN, ['backups.view', 'backups.export']))
            ->get('/admin/excel-exports')
            ->assertOk();
    }

    #[Test]
    public function право_смотреть_без_права_выгружать_прячет_кнопку(): void
    {
        $this->actingAs($this->admin(AdminAccess::ADMIN, ['backups.view']));

        Livewire::test(ExcelExports::class)->assertActionHidden('run');
    }

    // ── Кнопка ──────────────────────────────────────────────────────

    #[Test]
    public function кнопка_ставит_выгрузку_и_пишет_журнал(): void
    {
        Queue::fake();
        $actor = $this->admin(AdminAccess::SUPERADMIN);
        $this->actingAs($actor);

        Livewire::test(ExcelExports::class)
            ->callAction('run')
            ->assertNotified('Выгрузка запущена');

        Queue::assertPushed(RunDatabaseExport::class);

        $this->assertSame($actor->name, app(DatabaseExports::class)->all()[0]['requested_by']);
        $this->assertTrue(AdminAction::query()
            ->where('action', 'exported')
            ->where('section', 'backups')
            ->where('user_id', $actor->id)
            ->exists());
    }

    #[Test]
    public function пока_идёт_выгрузка_кнопка_недоступна(): void
    {
        Queue::fake();
        $this->actingAs($this->admin(AdminAccess::SUPERADMIN));

        app(DatabaseExports::class)->queue(null);

        Livewire::test(ExcelExports::class)->assertActionDisabled('run');
    }

    #[Test]
    public function список_показывает_готовую_выгрузку_со_ссылками(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPERADMIN));
        $run = $this->finishedRun();

        Livewire::test(ExcelExports::class)
            ->assertSee('готово')
            ->assertSee('Компании')
            ->assertSee('Объявления')
            ->assertSee(route('filament.admin.exports.download', ['run' => $run['id'], 'file' => $run['php']['files'][0]]), false)
            ->assertSee('не сверялась');
    }

    #[Test]
    public function книги_python_версии_отмечены_в_списке(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPERADMIN));
        $this->выгрузка('2026-09-27-100000-py00', [
            'engine' => 'python',
            'files' => ['savdex-companies-2026-09-27-1000.xlsx', 'savdex-listings-2026-09-27-1000.xlsx'],
            'php' => ['ok' => true, 'output' => ''],
            'python' => ['status' => 'match', 'self_check' => true, 'differences' => 0, 'problems' => []],
        ]);

        Livewire::test(ExcelExports::class)
            ->assertSee('книги Python-версии')
            ->assertSee('совпала')
            ->assertSee(route('filament.admin.exports.download', ['run' => '2026-09-27-100000-py00', 'file' => 'savdex-listings-2026-09-27-1000.xlsx']), false);
    }

    #[Test]
    public function старые_выгрузки_в_истории_по_прежнему_скачиваются(): void
    {
        // До переключения книги перечислялись в php.files, а files и engine не было
        $this->actingAs($this->admin(AdminAccess::SUPERADMIN));
        $this->выгрузка('2026-09-25-100000-old0', [
            'php' => ['ok' => true, 'output' => '', 'files' => ['savdex-companies-2026-09-25-1000.xlsx']],
            'python' => ['status' => 'match', 'differences' => 0, 'problems' => []],
        ]);

        Livewire::test(ExcelExports::class)
            ->assertSee('книги PHP-версии')
            ->assertSee(route('filament.admin.exports.download', ['run' => '2026-09-25-100000-old0', 'file' => 'savdex-companies-2026-09-25-1000.xlsx']), false);
    }

    /** Готовая выгрузка с заданным run.json — как её оставил бы воркер. */
    private function выгрузка(string $id, array $fields): void
    {
        Storage::disk('local')->put("exports/{$id}/run.json", json_encode([
            'id' => $id,
            'status' => 'done',
            'requested_by' => 'консоль',
            'queued_at' => now()->toIso8601String(),
            'finished_at' => now()->toIso8601String(),
            ...$fields,
        ], JSON_UNESCAPED_UNICODE));
    }

    // ── Скачивание ──────────────────────────────────────────────────

    #[Test]
    public function суперадмин_скачивает_и_это_в_журнале(): void
    {
        $actor = $this->admin(AdminAccess::SUPERADMIN);
        $run = $this->finishedRun();
        $file = $run['php']['files'][0];

        $this->actingAs($actor)
            ->get(route('filament.admin.exports.download', ['run' => $run['id'], 'file' => $file]))
            ->assertOk()
            ->assertDownload($file);

        $this->assertTrue(AdminAction::query()
            ->where('action', 'downloaded')
            ->where('user_id', $actor->id)
            ->where('note', 'like', "%{$file}%")
            ->exists());
    }

    #[Test]
    public function без_права_скачать_нельзя(): void
    {
        $run = $this->finishedRun();

        $this->actingAs($this->admin(AdminAccess::ADMIN, ['backups.view']))
            ->get(route('filament.admin.exports.download', ['run' => $run['id'], 'file' => $run['php']['files'][0]]))
            ->assertForbidden();
    }

    #[Test]
    public function гость_отправляется_на_вход(): void
    {
        $run = $this->finishedRun();

        $this->get(route('filament.admin.exports.download', ['run' => $run['id'], 'file' => $run['php']['files'][0]]))
            ->assertRedirect();
    }

    #[Test]
    public function служебные_и_выдуманные_файлы_не_отдаются(): void
    {
        $run = $this->finishedRun();
        $this->actingAs($this->admin(AdminAccess::SUPERADMIN));

        $this->get("/admin/exports/{$run['id']}/run.json")->assertNotFound();
        $this->get("/admin/exports/{$run['id']}/savdex-companies-1999-01-01-0000.xlsx")->assertNotFound();
        $this->get('/admin/exports/..%2F..%2F/savdex-companies-2026-01-01-0000.xlsx')->assertNotFound();
    }
}
