<?php

declare(strict_types=1);

namespace Tests\Feature\Crm;

use App\Filament\Resources\Communications\CommunicationResource;
use App\Filament\Resources\Contacts\ContactResource;
use App\Filament\Resources\Deals\DealResource;
use App\Filament\Resources\Leads\LeadResource;
use App\Filament\Resources\Tasks\TaskResource;
use App\Models\Crm\Deal;
use App\Models\Crm\Lead;
use App\Models\Crm\Task;
use App\Models\User;
use App\Support\AdminAccess;
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

        $this->assertFalse(LeadResource::canViewAny());
        $this->assertFalse(DealResource::canViewAny());
        $this->assertFalse(ContactResource::canViewAny());
        $this->assertFalse(CommunicationResource::canViewAny());
    }

    #[Test]
    public function контент_менеджер_в_crm_не_попадает(): void
    {
        $this->actingAs($this->admin(AdminAccess::CONTENT_MANAGER));

        $this->assertFalse(LeadResource::canViewAny());
        $this->assertFalse(TaskResource::canViewAny());
    }

    #[Test]
    public function продажи_видят_все_разделы_crm(): void
    {
        $this->actingAs($this->admin(AdminAccess::SALES));

        $this->assertTrue(LeadResource::canViewAny());
        $this->assertTrue(DealResource::canViewAny());
        $this->assertTrue(ContactResource::canViewAny());
        $this->assertTrue(TaskResource::canViewAny());
        $this->assertTrue(CommunicationResource::canViewAny());
    }

    /** Поддержка ведёт свои задачи и переписку, но лидов и сделок не видит. */
    #[Test]
    public function поддержка_видит_задачи_но_не_сделки(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPPORT));

        $this->assertTrue(TaskResource::canViewAny());
        $this->assertTrue(CommunicationResource::canViewAny());
        $this->assertTrue(ContactResource::canViewAny());
        $this->assertFalse(LeadResource::canViewAny());
        $this->assertFalse(DealResource::canViewAny());
    }

    // ── Область видимости ───────────────────────────────────────────

    #[Test]
    public function продавец_видит_своих_и_нераспределённых_лидов(): void
    {
        $sales = $this->admin(AdminAccess::SALES);
        $other = $this->admin(AdminAccess::SALES);

        $mine = Lead::factory()->create(['owner_id' => $sales->id]);
        $free = Lead::factory()->create(['owner_id' => null]);
        $alien = Lead::factory()->create(['owner_id' => $other->id]);

        $this->actingAs($sales);

        $visible = LeadResource::getEloquentQuery()->pluck('id')->all();

        $this->assertContains($mine->id, $visible);
        $this->assertContains($free->id, $visible, 'нераспределённый виден всем продавцам');
        $this->assertNotContains($alien->id, $visible, 'чужой лид не виден');
    }

    #[Test]
    public function руководитель_видит_всех_лидов(): void
    {
        $sales = $this->admin(AdminAccess::SALES);
        Lead::factory()->create(['owner_id' => $sales->id]);
        Lead::factory()->create(['owner_id' => null]);

        $this->actingAs($this->admin(AdminAccess::ADMIN));

        $this->assertSame(2, LeadResource::getEloquentQuery()->count());
    }

    /** У сделок «ничьих» не бывает: сделка выросла из чьей-то работы. */
    #[Test]
    public function продавец_не_видит_чужих_сделок(): void
    {
        $sales = $this->admin(AdminAccess::SALES);
        $other = $this->admin(AdminAccess::SALES);

        $mine = Deal::factory()->create(['owner_id' => $sales->id]);
        $alien = Deal::factory()->create(['owner_id' => $other->id]);

        $this->actingAs($sales);

        $visible = DealResource::getEloquentQuery()->pluck('id')->all();

        $this->assertContains($mine->id, $visible);
        $this->assertNotContains($alien->id, $visible);
    }

    /**
     * Скрытая строка защищает от случайности, прямая ссылка — нет.
     *
     * Список можно сузить запросом, но адрес чужой карточки вводится
     * руками, и там нужна отдельная проверка.
     */
    #[Test]
    public function чужую_карточку_нельзя_открыть_по_ссылке(): void
    {
        $sales = $this->admin(AdminAccess::SALES);
        $other = $this->admin(AdminAccess::SALES);

        $alien = Lead::factory()->create(['owner_id' => $other->id]);

        $this->actingAs($sales);

        $this->assertFalse(LeadResource::canView($alien));
        $this->assertFalse(LeadResource::canEdit($alien));
        $this->assertFalse(LeadResource::canDelete($alien));
    }

    #[Test]
    public function нераспределённый_лид_править_можно(): void
    {
        $sales = $this->admin(AdminAccess::SALES);
        $free = Lead::factory()->create(['owner_id' => null]);

        $this->actingAs($sales);

        $this->assertTrue(LeadResource::canEdit($free));
    }

    #[Test]
    public function руководителю_чужие_записи_открыты(): void
    {
        $sales = $this->admin(AdminAccess::SALES);
        $alien = Lead::factory()->create(['owner_id' => $sales->id]);

        $this->actingAs($this->admin(AdminAccess::ADMIN));

        $this->assertTrue(LeadResource::canEdit($alien));
    }

    /** Задачи сужаются по исполнителю, а не по автору: список дел — про «мне». */
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

        $visible = TaskResource::getEloquentQuery()->pluck('id')->all();

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
