<?php

declare(strict_types=1);

namespace Tests\Feature\Support;

use App\Filament\Resources\Tickets\Pages\ListTickets;
use App\Filament\Resources\Tickets\TicketResource;
use App\Models\AdminAction;
use App\Models\Support\Message;
use App\Models\Support\Ticket;
use App\Models\User;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Обращения в поддержку.
 *
 * Главное здесь — что внутренняя заметка остаётся внутренней, и что
 * обращение от того, кто не смог войти, не теряется.
 */
class TicketsTest extends TestCase
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

    // ── Кто видит раздел ────────────────────────────────────────────

    #[Test]
    public function обращения_видят_поддержка_админ_и_суперадмин(): void
    {
        foreach (AdminAccess::ROLES as $role => $label) {
            $this->actingAs($this->admin($role));

            $expected = in_array($role, [
                AdminAccess::SUPERADMIN, AdminAccess::ADMIN, AdminAccess::SUPPORT,
            ], true);

            $this->assertSame($expected, TicketResource::canViewAny(), $label);
        }
    }

    #[Test]
    public function поддержка_не_видит_финансов_но_видит_обращения(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPPORT));

        $this->assertTrue(AdminAccess::allows('support.edit'));
        $this->assertFalse(AdminAccess::allows('payments.view'));
    }

    // ── Работа с обращением ─────────────────────────────────────────

    #[Test]
    public function сотрудник_берёт_обращение(): void
    {
        $support = $this->admin(AdminAccess::SUPPORT);
        $this->actingAs($support);

        $ticket = Ticket::factory()->create(['assignee_id' => null]);

        Livewire::test(ListTickets::class)->callTableAction('take', $ticket);

        $ticket->refresh();

        $this->assertSame($support->id, $ticket->assignee_id);
        $this->assertSame(Ticket::STATUS_WORKING, $ticket->status);
    }

    /** Ответ клиенту переводит обращение в ожидание: мяч на его стороне. */
    #[Test]
    public function ответ_клиенту_переводит_в_ожидание(): void
    {
        $support = $this->admin(AdminAccess::SUPPORT);
        $this->actingAs($support);

        $ticket = Ticket::factory()->create(['status' => Ticket::STATUS_WORKING]);

        Livewire::test(ListTickets::class)->callTableAction('reply', $ticket, [
            'body' => 'Письмо отправлено повторно, проверьте папку «Спам».',
            'is_internal' => false,
        ]);

        $ticket->refresh();

        $this->assertSame(Ticket::STATUS_WAITING, $ticket->status);
        $this->assertNotNull($ticket->last_reply_at);

        $message = Message::sole();

        $this->assertTrue($message->from_staff);
        $this->assertFalse($message->is_internal);
    }

    /**
     * Внутренняя заметка не уезжает клиенту и не меняет статус.
     *
     * Клиент ничего не получил — ждать его нечего, а обращение,
     * ушедшее в «ждёт ответа» после заметки для своих, выпадет из
     * работы молча.
     */
    #[Test]
    public function внутренняя_заметка_остаётся_внутренней(): void
    {
        $support = $this->admin(AdminAccess::SUPPORT);
        $this->actingAs($support);

        $ticket = Ticket::factory()->create(['status' => Ticket::STATUS_WORKING]);

        Livewire::test(ListTickets::class)->callTableAction('reply', $ticket, [
            'body' => 'Клиент пишет третий раз по одному и тому же, вести аккуратно.',
            'is_internal' => true,
        ]);

        $ticket->refresh();

        $this->assertSame(Ticket::STATUS_WORKING, $ticket->status, 'статус не меняется');

        $this->assertTrue(Message::sole()->is_internal);
        $this->assertSame(0, Message::query()->visibleToClient()->count(), 'клиент заметку не увидит');
    }

    #[Test]
    public function закрытие_и_переоткрытие_ведут_дату(): void
    {
        $support = $this->admin(AdminAccess::SUPPORT);
        $this->actingAs($support);

        $ticket = Ticket::factory()->create(['status' => Ticket::STATUS_WORKING]);

        Livewire::test(ListTickets::class)->callTableAction('close', $ticket);

        $this->assertNotNull($ticket->fresh()->closed_at);

        Livewire::test(ListTickets::class)
            ->removeTableFilter('open')
            ->callTableAction('close', $ticket->fresh());

        $ticket->refresh();

        $this->assertSame(Ticket::STATUS_WORKING, $ticket->status);
        $this->assertNull($ticket->closed_at, 'переоткрытое обращение не считается закрытым');
    }

    // ── Автор обращения ─────────────────────────────────────────────

    /**
     * Обращение от того, кто не смог войти, — самое срочное.
     *
     * Если бы автор хранился только ссылкой, такое обращение приходило
     * бы без имени и почты, и ответить было бы некому.
     */
    #[Test]
    public function обращение_без_учётной_записи_не_теряет_автора(): void
    {
        $ticket = Ticket::factory()->create([
            'user_id' => null,
            'author_name' => 'Пётр Сидоров',
            'author_email' => 'petr@example.com',
        ]);

        $this->assertSame('Пётр Сидоров', $ticket->author());
        $this->assertSame('petr@example.com', $ticket->authorEmail());
    }

    #[Test]
    public function у_зарегистрированного_берётся_имя_из_учётной_записи(): void
    {
        $user = User::factory()->create(['name' => 'Иван Клиентов', 'email' => 'ivan@savdex.uz']);

        $ticket = Ticket::factory()->create([
            'user_id' => $user->id,
            'author_name' => 'опечатка в форме',
        ]);

        $this->assertSame('Иван Клиентов', $ticket->author());
        $this->assertSame('ivan@savdex.uz', $ticket->authorEmail());
    }

    // ── След в журнале ──────────────────────────────────────────────

    #[Test]
    public function ответ_попадает_в_журнал(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPPORT));

        $ticket = Ticket::factory()->create();

        Livewire::test(ListTickets::class)->callTableAction('reply', $ticket, [
            'body' => 'Разобрались, всё работает.',
            'is_internal' => false,
        ]);

        $entry = AdminAction::where('section', 'support')
            ->whereNotNull('note')
            ->first();

        $this->assertNotNull($entry);
        $this->assertSame('Ответ клиенту', $entry->note);
    }
}
