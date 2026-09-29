<?php

declare(strict_types=1);

namespace Tests\Feature\Crm;

use App\Models\Crm\Task;
use App\Models\User;
use App\Support\AdminAccess;
use App\Support\AdminScope;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Кто и что видит в CRM.
 *
 * Главное здесь — область видимости: продавец работает со своими
 * записями, руководитель со всеми, и это одна и та же страница
 * с одним и тем же правом.
 */
class CrmAccessTest extends TestCase
{
    use RefreshDatabase;

    private function admin(string $role): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => $role,
            'status' => 'active',
        ]);
    }

    // ── Кто видит разделы ───────────────────────────────────────────

    #[Test]
    public function модератор_в_crm_не_попадает(): void
    {
        $this->actingAs($this->admin(AdminAccess::MODERATOR));

        $this->assertFalse(AdminAccess::allows('leads.view'));
        $this->assertFalse(AdminAccess::allows('deals.view'));
        $this->assertFalse(AdminAccess::allows('contacts.view'));
        $this->assertFalse(AdminAccess::allows('communications.view'));
    }

    #[Test]
    public function контент_менеджер_в_crm_не_попадает(): void
    {
        $this->actingAs($this->admin(AdminAccess::CONTENT_MANAGER));

        $this->assertFalse(AdminAccess::allows('leads.view'));
        $this->assertFalse(AdminAccess::allows('tasks.view'));
    }

    #[Test]
    public function продажи_видят_все_разделы_crm(): void
    {
        $this->actingAs($this->admin(AdminAccess::SALES));

        $this->assertTrue(AdminAccess::allows('leads.view'));
        $this->assertTrue(AdminAccess::allows('deals.view'));
        $this->assertTrue(AdminAccess::allows('contacts.view'));
        $this->assertTrue(AdminAccess::allows('tasks.view'));
        $this->assertTrue(AdminAccess::allows('communications.view'));
    }

    /** Поддержка ведёт свои задачи и переписку, но лидов и сделок не видит. */
    #[Test]
    public function поддержка_видит_задачи_но_не_сделки(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPPORT));

        $this->assertTrue(AdminAccess::allows('tasks.view'));
        $this->assertTrue(AdminAccess::allows('communications.view'));
        $this->assertTrue(AdminAccess::allows('contacts.view'));
        $this->assertFalse(AdminAccess::allows('leads.view'));
        $this->assertFalse(AdminAccess::allows('deals.view'));
    }

    // ── Область видимости ───────────────────────────────────────────

    /**
     * Задачи сужаются по исполнителю, а не по автору: список дел — про
     * «мне». Так считают счётчик у пункта меню и виджет «Задачи на
     * сегодня»; сам раздел — на Python (tests/test_crm_tasks_admin.py).
     */
    #[Test]
    public function задачи_сужаются_по_исполнителю(): void
    {
        $sales = $this->admin(AdminAccess::SALES);
        $other = $this->admin(AdminAccess::SALES);

        $mine = Task::factory()->create(['assignee_id' => $sales->id]);
        // Завёл он, а делать не ему — в своём списке дел быть не должно
        $authored = Task::factory()->create([
            'assignee_id' => $other->id,
            'created_by' => $sales->id,
        ]);

        $this->actingAs($sales);

        $visible = AdminScope::apply(Task::query(), 'tasks', 'assignee_id')->pluck('id')->all();

        $this->assertContains($mine->id, $visible);
        $this->assertNotContains($authored->id, $visible);
    }

    /** Контакты общие: один снабженец бывает и в лиде, и в чужой сделке. */
    #[Test]
    public function контакты_не_делятся_по_ответственным(): void
    {
        $sales = $this->admin(AdminAccess::SALES);

        $this->assertFalse($sales->adminScopeIsOwn('contacts'));
    }
}
