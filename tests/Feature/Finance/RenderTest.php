<?php

declare(strict_types=1);

namespace Tests\Feature\Finance;

use App\Filament\Pages\FinanceOperations;
use App\Filament\Pages\Roles;
use App\Filament\Resources\AdminActions\Pages\ListAdminActions;
use App\Filament\Resources\Communications\Pages\ListCommunications;
use App\Filament\Resources\Contacts\Pages\ListContacts;
use App\Filament\Resources\Deals\Pages\ListDeals;
use App\Filament\Resources\Leads\Pages\ListLeads;
use App\Filament\Resources\Refunds\Pages\ListRefunds;
use App\Filament\Resources\Tasks\Pages\ListTasks;
use App\Filament\Resources\Tickets\Pages\ListTickets;
use App\Models\Company;
use App\Models\Crm\Communication;
use App\Models\Crm\Contact;
use App\Models\Crm\Deal;
use App\Models\Crm\Lead;
use App\Models\Crm\Task;
use App\Models\Payment;
use App\Models\Refund;
use App\Models\Support\Ticket;
use App\Models\User;
use App\Models\WalletTransaction;
use App\Support\AdminAccess;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Livewire\Livewire;
use PHPUnit\Framework\Attributes\DataProvider;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Каждая страница обязана открываться — и пустой, и с данными.
 *
 * Прошлая версия этого теста проверяла только пустые страницы, и этого
 * оказалось мало: «Финансовые операции» падали ровно тогда, когда в
 * таблице появлялась хоть одна строка. Связь user у движения по
 * кошельку была объявлена в запросе, но не в модели, а без строк
 * подгружать нечего — ошибка и не всплывала.
 *
 * Поэтому здесь каждая страница рисуется дважды: пустой и с записью,
 * у которой заполнены все связи. Тест скучный, но ловит целый класс
 * поломок, который иначе находит пользователь.
 */
class RenderTest extends TestCase
{
    use RefreshDatabase;

    /**
     * @return array<string, array{class-string}>
     */
    public static function страницы(): array
    {
        return [
            'журнал действий' => [ListAdminActions::class],
            'роли и права' => [Roles::class],
            'лиды' => [ListLeads::class],
            'сделки' => [ListDeals::class],
            'контакты' => [ListContacts::class],
            'задачи' => [ListTasks::class],
            'коммуникации' => [ListCommunications::class],
            'обращения' => [ListTickets::class],
            'возвраты' => [ListRefunds::class],
            'финансовые операции' => [FinanceOperations::class],
        ];
    }

    private function superadmin(): User
    {
        $user = User::factory()->create([
            'is_admin' => true,
            'admin_role' => AdminAccess::SUPERADMIN,
            'status' => 'active',
        ]);

        $this->actingAs($user);

        return $user;
    }

    /**
     * По одной записи в каждый раздел, со всеми заполненными связями.
     *
     * Пустые поля связей не годятся: именно на подгрузке связи и
     * ломалось. Где связь необязательна, заполняем её всё равно —
     * проверяем худший случай, а не самый простой.
     */
    private function fill(User $actor): void
    {
        $company = Company::factory()->create();
        $contact = Contact::factory()->create(['company_id' => $company->id]);

        $lead = Lead::factory()->create([
            'company_id' => $company->id,
            'contact_id' => $contact->id,
            'owner_id' => $actor->id,
        ]);

        $deal = Deal::factory()->create([
            'company_id' => $company->id,
            'contact_id' => $contact->id,
            'lead_id' => $lead->id,
            'owner_id' => $actor->id,
        ]);

        Task::factory()->create([
            'assignee_id' => $actor->id,
            'created_by' => $actor->id,
            'subject_type' => $deal::class,
            'subject_id' => $deal->id,
        ]);

        Communication::factory()->create([
            'author_id' => $actor->id,
            'contact_id' => $contact->id,
            'subject_type' => $lead::class,
            'subject_id' => $lead->id,
        ]);

        Ticket::factory()->create([
            'user_id' => $actor->id,
            'company_id' => $company->id,
            'assignee_id' => $actor->id,
        ]);

        $payment = Payment::create([
            'company_id' => $company->id,
            'purpose' => 'credits',
            'description' => 'Пакет контактов',
            'amount' => 1000000,
            'currency' => 'UZS',
            'status' => 'paid',
            'paid_at' => now(),
        ]);

        Refund::factory()->create([
            'payment_id' => $payment->id,
            'company_id' => $company->id,
            'created_by' => $actor->id,
        ]);

        // Движение с автором и без: колонка «кто провёл» показывает
        // имя в первом случае и «автоматически» во втором
        foreach ([$actor->id, null] as $userId) {
            WalletTransaction::create([
                'company_id' => $company->id,
                'user_id' => $userId,
                'kind' => 'credits',
                'amount' => $userId === null ? -1 : 50,
                'balance_after' => 49,
                'reason' => $userId === null ? 'unlock' : 'purchase',
                'comment' => 'проверка',
            ]);
        }
    }

    /**
     * @param  class-string  $page
     */
    #[Test]
    #[DataProvider('страницы')]
    public function страница_открывается_пустой(string $page): void
    {
        $this->superadmin();

        Livewire::test($page)->assertOk();
    }

    /**
     * @param  class-string  $page
     */
    #[Test]
    #[DataProvider('страницы')]
    public function страница_открывается_с_данными(string $page): void
    {
        $this->fill($this->superadmin());

        Livewire::test($page)->assertOk();
    }
}
