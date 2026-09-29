<?php

declare(strict_types=1);

namespace Tests\Feature\Support;

use App\Models\Support\Ticket;
use App\Models\User;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Обращения в поддержку.
 *
 * Раздел — в админке на Python (tests/test_support_admin.py: «Взять»,
 * ответ и внутренняя заметка, закрытие, журнал); здесь — права и
 * правила модели: обращение от того, кто не смог войти, не теряется.
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

            $this->assertSame($expected, AdminAccess::allows('support.view'), $label);
        }
    }

    #[Test]
    public function поддержка_не_видит_финансов_но_видит_обращения(): void
    {
        $this->actingAs($this->admin(AdminAccess::SUPPORT));

        $this->assertTrue(AdminAccess::allows('support.edit'));
        $this->assertFalse(AdminAccess::allows('payments.view'));
    }

    /** Ticket::saving: дата закрытия ставится и снимается сама. */
    #[Test]
    public function закрытие_и_переоткрытие_ведут_дату(): void
    {
        $ticket = Ticket::factory()->create(['status' => Ticket::STATUS_WORKING]);

        $ticket->update(['status' => Ticket::STATUS_CLOSED]);
        $this->assertNotNull($ticket->fresh()->closed_at);

        $ticket->update(['status' => Ticket::STATUS_WORKING]);
        $this->assertNull($ticket->fresh()->closed_at, 'переоткрытое обращение не считается закрытым');
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
}
