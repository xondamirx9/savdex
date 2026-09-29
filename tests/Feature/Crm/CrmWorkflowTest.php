<?php

declare(strict_types=1);

namespace Tests\Feature\Crm;

use App\Filament\Resources\Tasks\Pages\ListTasks;
use App\Models\AdminAction;
use App\Models\Crm\Deal;
use App\Models\Crm\Lead;
use App\Models\Crm\Task;
use App\Models\User;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Работа с CRM: как лид проходит путь до сделки.
 *
 * Проверяется не форма, а те действия, ради которых CRM и заводят.
 * Лиды и сделки — в админке на Python (tests/test_crm_leads_admin.py);
 * здесь — правила моделей и задачи.
 */
class CrmWorkflowTest extends TestCase
{
    use RefreshDatabase;

    private function sales(): User
    {
        return User::factory()->create([
            'is_admin' => true,
            'admin_role' => AdminAccess::SALES,
            'status' => 'active',
        ]);
    }

    // ── Сделка ──────────────────────────────────────────────────────

    /**
     * Дата закрытия ставится сама.
     *
     * Просить человека отметить и этап, и дату — значит получить
     * выигранные сделки без даты и отчёт, который не считается.
     */
    #[Test]
    public function дата_закрытия_проставляется_сама(): void
    {
        $deal = Deal::factory()->create(['stage' => Deal::STAGE_NEGOTIATION]);

        $this->assertNull($deal->closed_at);

        $deal->forceFill(['stage' => Deal::STAGE_WON])->save();

        $this->assertNotNull($deal->fresh()->closed_at);
    }

    /** Вернули сделку в работу — дата закрытия обязана уйти. */
    #[Test]
    public function возврат_сделки_в_работу_снимает_дату_закрытия(): void
    {
        $deal = Deal::factory()->create(['stage' => Deal::STAGE_WON]);

        $this->assertNotNull($deal->fresh()->closed_at);

        $deal->forceFill(['stage' => Deal::STAGE_NEGOTIATION])->save();

        $this->assertNull($deal->fresh()->closed_at);
    }

    #[Test]
    public function сумма_читается_человеком(): void
    {
        $deal = Deal::factory()->create(['amount' => 46386000, 'currency' => 'UZS']);

        $this->assertSame('46 386 000 сум', $deal->money());
    }

    // ── Задача ──────────────────────────────────────────────────────

    #[Test]
    public function задача_закрывается_одной_кнопкой(): void
    {
        $sales = $this->sales();
        $this->actingAs($sales);

        $task = Task::factory()->create(['assignee_id' => $sales->id]);

        Livewire::test(ListTasks::class)->callTableAction('done', $task);

        $this->assertTrue($task->fresh()->isDone());

        // Выполненная задача уходит из списка по умолчанию — чтобы
        // вернуть её в работу, фильтр надо снять
        Livewire::test(ListTasks::class)
            ->removeTableFilter('open')
            ->callTableAction('done', $task->fresh());

        $this->assertFalse($task->fresh()->isDone());
    }

    /**
     * Выполненная задача просроченной не считается.
     *
     * Список «горит» показывает то, что ещё требует действий, а не
     * упрекает за прошлое.
     */
    #[Test]
    public function выполненная_задача_не_считается_просроченной(): void
    {
        $overdue = Task::factory()->create(['due_at' => now()->subDay(), 'done_at' => null]);
        $late = Task::factory()->create(['due_at' => now()->subDay(), 'done_at' => now()]);

        $this->assertTrue($overdue->isOverdue());
        $this->assertFalse($late->isOverdue());
    }

    #[Test]
    public function задача_без_срока_не_просрочена(): void
    {
        $this->assertFalse(Task::factory()->create(['due_at' => null])->isOverdue());
    }

    // ── След в журнале ──────────────────────────────────────────────

    #[Test]
    public function работа_в_crm_попадает_в_журнал(): void
    {
        $sales = $this->sales();
        $this->actingAs($sales);

        $lead = Lead::factory()->create(['owner_id' => $sales->id]);
        $lead->forceFill(['status' => Lead::STATUS_QUALIFIED])->save();

        $this->assertTrue(
            AdminAction::where('section', 'leads')->where('action', 'updated')->exists(),
        );
    }
}
