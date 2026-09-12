<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\Company;
use App\Models\ItTask;
use App\Models\ItTaskFile;
use App\Models\MessageThread;
use App\Models\Plan;
use App\Models\Subscription;
use App\Models\User;
use App\Models\Wallet;
use App\Services\SubscriptionService;
use Database\Seeders\PlanSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Http\UploadedFile;
use Illuminate\Support\Facades\Storage;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * IT-услуги: заказчик публикует задачу, IT-исполнитель откликается.
 *
 * Публикация — без модерации, сразу на витрину. Отклик доступен
 * только компаниям с ролью IT-исполнителя и списывает квоту откликов
 * тарифа ровно так же, как отклик на объявление.
 */
class ItTaskTest extends TestCase
{
    use RefreshDatabase;

    private Company $customer;

    private User $customerUser;

    private Company $provider;

    private User $providerUser;

    protected function setUp(): void
    {
        parent::setUp();

        $this->seed(PlanSeeder::class);

        $this->customer = Company::factory()->create();
        $this->customerUser = User::factory()->for($this->customer)->create(['email_verified_at' => now()]);

        $this->provider = Company::factory()->create([
            'is_it_provider' => true,
            'it_specializations' => ['web', 'integration'],
        ]);
        $this->providerUser = User::factory()->for($this->provider)->create(['email_verified_at' => now()]);
    }

    /** @return array<string, mixed> */
    private function payload(array $overrides = []): array
    {
        return [
            'title' => 'Интернет-магазин стройматериалов с оплатой картой',
            'description' => 'Нужен магазин на Laravel: каталог, корзина, оплата Uzum, интеграция с 1С по остаткам.',
            'service_type' => 'web',
            'stack' => ['Laravel', 'React', 'Laravel'],
            'budget_type' => 'range',
            'budget_from' => 20000000,
            'budget_to' => 50000000,
            'currency' => 'UZS',
            'deadline_at' => now()->addDays(45)->format('Y-m-d'),
            ...$overrides,
        ];
    }

    // ── Публикация ───────────────────────────────────────────

    #[Test]
    public function задача_публикуется_сразу_и_видна_на_витрине(): void
    {
        Storage::fake('local');

        $this->actingAs($this->customerUser)
            ->post('/cabinet/it-tasks', $this->payload([
                'files' => [UploadedFile::fake()->create('tz.pdf', 120, 'application/pdf')],
            ]))
            ->assertRedirect('/cabinet/it-tasks')
            ->assertSessionHasNoErrors();

        $task = ItTask::firstOrFail();

        $this->assertSame(ItTask::STATUS_ACTIVE, $task->status);
        $this->assertSame($this->customer->id, $task->company_id);
        $this->assertSame(['Laravel', 'React'], $task->stack, 'Дубли стека убираются');
        $this->assertNotNull($task->slug);
        $this->assertSame(1, $task->files()->count());
        Storage::disk('local')->assertExists($task->files()->first()->file_path);

        $this->get('/it-services')->assertInertia(fn (AssertableInertia $page) => $page
            ->component('it-tasks/Index')
            ->where('total', 1)
            ->where('tasks.data.0.title', $task->title)
            ->where('tasks.data.0.budget_type', 'range'));

        $this->get("/it-services/{$task->slug}")->assertOk()->assertInertia(fn (AssertableInertia $page) => $page
            ->component('it-tasks/Show')
            ->where('task.files.0.title', 'tz.pdf'));
    }

    #[Test]
    public function короткое_описание_и_кривой_бюджет_не_проходят(): void
    {
        $this->actingAs($this->customerUser)
            ->from('/cabinet/it-tasks/create')
            ->post('/cabinet/it-tasks', $this->payload([
                'description' => 'Коротко',
                'budget_from' => 50000000,
                'budget_to' => 20000000,
            ]))
            ->assertRedirect('/cabinet/it-tasks/create')
            ->assertSessionHasErrors(['description', 'budget_to']);

        $this->assertSame(0, ItTask::count());
    }

    #[Test]
    public function договорной_бюджет_обнуляет_суммы(): void
    {
        $this->actingAs($this->customerUser)
            ->post('/cabinet/it-tasks', $this->payload(['budget_type' => 'negotiable']))
            ->assertSessionHasNoErrors();

        $task = ItTask::firstOrFail();
        $this->assertNull($task->budget_from);
        $this->assertNull($task->budget_to);
    }

    #[Test]
    public function без_компании_задачу_не_создать(): void
    {
        $lonely = User::factory()->create(['company_id' => null, 'email_verified_at' => now()]);

        $this->actingAs($lonely)->get('/cabinet/it-tasks/create')->assertRedirect('/cabinet/company');
    }

    #[Test]
    public function чужую_задачу_нельзя_ни_править_ни_закрыть(): void
    {
        $task = ItTask::factory()->create(['company_id' => $this->customer->id]);

        $this->actingAs($this->providerUser)->get("/cabinet/it-tasks/{$task->id}/edit")->assertNotFound();
        $this->actingAs($this->providerUser)->post("/cabinet/it-tasks/{$task->id}/close")->assertNotFound();
        $this->actingAs($this->providerUser)->delete("/cabinet/it-tasks/{$task->id}")->assertNotFound();

        $this->assertTrue($task->fresh()->isActive());
    }

    #[Test]
    public function закрытая_задача_уходит_с_витрины_но_остаётся_заказчику(): void
    {
        $task = ItTask::factory()->create(['company_id' => $this->customer->id]);

        $this->actingAs($this->customerUser)->post("/cabinet/it-tasks/{$task->id}/close")->assertRedirect();

        $this->assertSame(ItTask::STATUS_CLOSED, $task->fresh()->status);
        $this->actingAs($this->customerUser)->get("/it-services/{$task->slug}")->assertOk();

        // Гость и посторонние — 404: откликаться в пустоту незачем
        auth()->logout();
        $this->get("/it-services/{$task->slug}")->assertNotFound();
        $this->get('/it-services')->assertInertia(fn (AssertableInertia $page) => $page->where('total', 0));
    }

    // ── Отклики ──────────────────────────────────────────────

    #[Test]
    public function исполнитель_откликается_и_попадает_в_чат_со_списанием_квоты(): void
    {
        $task = ItTask::factory()->create(['company_id' => $this->customer->id]);

        $this->actingAs($this->providerUser)
            ->post("/it-services/{$task->id}/respond", ['body' => 'Делали похожие магазины, готовы обсудить.'])
            ->assertRedirect()
            ->assertSessionHasNoErrors();

        $thread = MessageThread::firstOrFail();

        $this->assertSame($task->id, $thread->it_task_id);
        $this->assertNull($thread->listing_id);
        $this->assertSame($this->provider->id, $thread->buyer_company_id);
        $this->assertSame($this->customer->id, $thread->seller_company_id);
        $this->assertSame(1, $thread->messages()->count());
        $this->assertSame(1, $task->fresh()->responses_count);
        $this->assertSame(1, (int) Wallet::where('company_id', $this->provider->id)->value('responses_used_this_period'));

        // Чат показывает тему разговора — задачу
        $this->actingAs($this->customerUser)
            ->get("/cabinet/chats/{$thread->id}")
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('thread.task.title', $task->title)
                ->where('thread.listing', null));
    }

    #[Test]
    public function повторный_отклик_продолжает_разговор_без_второго_списания(): void
    {
        $task = ItTask::factory()->create(['company_id' => $this->customer->id]);

        $this->actingAs($this->providerUser)->post("/it-services/{$task->id}/respond", ['body' => 'Первое сообщение']);
        $this->actingAs($this->providerUser)->post("/it-services/{$task->id}/respond", ['body' => 'Второе сообщение']);

        $this->assertSame(1, MessageThread::count());
        $this->assertSame(2, MessageThread::first()->messages()->count());
        $this->assertSame(1, $task->fresh()->responses_count);
        $this->assertSame(1, (int) Wallet::where('company_id', $this->provider->id)->value('responses_used_this_period'));
    }

    #[Test]
    public function компания_без_роли_исполнителя_откликнуться_не_может(): void
    {
        $task = ItTask::factory()->create(['company_id' => $this->customer->id]);
        $plain = Company::factory()->create(['is_it_provider' => false]);
        $plainUser = User::factory()->for($plain)->create(['email_verified_at' => now()]);

        $this->actingAs($plainUser)
            ->post("/it-services/{$task->id}/respond", ['body' => 'Хочу взять заказ'])
            ->assertSessionHasErrors('body');

        $this->assertSame(0, MessageThread::count());

        // И карточка говорит об этом прямо
        $this->actingAs($plainUser)->get("/it-services/{$task->slug}")
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('respond.provider', false)
                ->where('respond.owner', false));
    }

    #[Test]
    public function на_свою_и_на_закрытую_задачу_откликнуться_нельзя(): void
    {
        $own = ItTask::factory()->create(['company_id' => $this->provider->id]);
        $closed = ItTask::factory()->closed()->create(['company_id' => $this->customer->id]);

        $this->actingAs($this->providerUser)->post("/it-services/{$own->id}/respond", ['body' => 'Себе'])->assertSessionHasErrors('body');
        $this->actingAs($this->providerUser)->post("/it-services/{$closed->id}/respond", ['body' => 'Поздно'])->assertSessionHasErrors('body');

        $this->assertSame(0, MessageThread::count());
    }

    #[Test]
    public function исчерпанный_лимит_откликов_действует_и_на_задачи(): void
    {
        app(SubscriptionService::class)->assign(
            $this->provider,
            Plan::where('code', 'business')->firstOrFail(),
            days: 30,
            source: Subscription::SOURCE_MANUAL,
            reason: 'Тест',
        );
        $limit = (int) Plan::where('code', 'business')->value('responses_limit');
        Wallet::firstOrCreate(['company_id' => $this->provider->id])
            ->forceFill(['responses_used_this_period' => $limit])->save();

        $task = ItTask::factory()->create(['company_id' => $this->customer->id]);

        $this->actingAs($this->providerUser)
            ->post("/it-services/{$task->id}/respond", ['body' => 'Ещё один'])
            ->assertSessionHasErrors('body');

        $this->assertSame(0, MessageThread::count());
    }

    // ── Файлы ────────────────────────────────────────────────

    #[Test]
    public function файлы_тз_доступны_только_вошедшим(): void
    {
        Storage::fake('local');
        $task = ItTask::factory()->create(['company_id' => $this->customer->id]);
        $path = UploadedFile::fake()->create('tz.pdf', 10, 'application/pdf')->store("it-tasks/{$task->id}", 'local');
        $file = ItTaskFile::create(['it_task_id' => $task->id, 'title' => 'tz.pdf', 'file_path' => $path, 'file_size' => 10240, 'mime' => 'application/pdf']);

        $this->get("/it-services/files/{$file->id}")->assertRedirect('/login');
        $this->actingAs($this->providerUser)->get("/it-services/files/{$file->id}")->assertOk();

        // У закрытой задачи файлы видит только заказчик
        $task->forceFill(['status' => ItTask::STATUS_CLOSED])->save();
        $this->actingAs($this->providerUser)->get("/it-services/files/{$file->id}")->assertNotFound();
        $this->actingAs($this->customerUser)->get("/it-services/files/{$file->id}")->assertOk();
    }

    // ── Профиль исполнителя ──────────────────────────────────

    #[Test]
    public function роль_исполнителя_включается_в_профиле_и_видна_на_визитке(): void
    {
        $this->actingAs($this->customerUser)
            ->patch('/cabinet/company', [
                'name' => $this->customer->name,
                'is_it_provider' => true,
                'it_specializations' => ['mobile', 'design', 'unknown'],
            ])
            ->assertSessionHasErrors(['it_specializations.2']);

        $this->actingAs($this->customerUser)
            ->patch('/cabinet/company', [
                'name' => $this->customer->name,
                'is_it_provider' => true,
                'it_specializations' => ['mobile', 'design'],
            ])
            ->assertSessionHasNoErrors();

        $company = $this->customer->fresh();
        $this->assertTrue($company->is_it_provider);
        $this->assertSame(['mobile', 'design'], $company->it_specializations);

        $this->get("/company/{$company->slug}")->assertInertia(fn (AssertableInertia $page) => $page
            ->where('company.is_it_provider', true)
            ->where('company.it_specializations', ['Мобильные приложения', 'Дизайн и UX']));
    }

    #[Test]
    public function фильтр_по_виду_услуги_и_поиск_работают(): void
    {
        ItTask::factory()->create(['company_id' => $this->customer->id, 'title' => 'Мобильное приложение для дилеров', 'service_type' => 'mobile']);
        ItTask::factory()->create(['company_id' => $this->customer->id, 'title' => 'Интеграция сайта с 1С', 'service_type' => 'integration', 'stack' => ['1С', 'REST']]);

        $this->get('/it-services?type=mobile')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('total', 1)
            ->where('tasks.data.0.title', 'Мобильное приложение для дилеров'));

        $this->get('/it-services?q=rest')->assertInertia(fn (AssertableInertia $page) => $page
            ->where('total', 1)
            ->where('tasks.data.0.service_type', 'integration'));
    }
}
