<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\Company;
use App\Models\Listing;
use App\Models\MessageThread;
use App\Models\Plan;
use App\Models\Subscription;
use App\Models\User;
use App\Models\UserNotification;
use App\Models\Wallet;
use App\Services\ChatService;
use App\Services\SubscriptionService;
use Database\Seeders\PlanSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Testing\TestResponse;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Чат между компаниями: отклик на объявление и переписка.
 *
 * Отклик — квота тарифа (responses_limit): списывается за новый
 * разговор, сообщения внутри бесплатны. Цена ошибки — бесплатный обход
 * лимита или чтение чужой переписки, поэтому лимиты, права доступа
 * и маскировка контактов проверяются отдельно.
 */
class ChatTest extends TestCase
{
    use RefreshDatabase;

    private Company $seller;

    private User $sellerUser;

    private Company $buyer;

    private User $buyerUser;

    private Listing $listing;

    protected function setUp(): void
    {
        parent::setUp();

        $this->seed(PlanSeeder::class);

        $this->seller = Company::factory()->create();
        $this->sellerUser = User::factory()->for($this->seller)->create(['email_verified_at' => now()]);

        $this->buyer = Company::factory()->create();
        $this->buyerUser = User::factory()->for($this->buyer)->create(['email_verified_at' => now()]);

        $this->listing = Listing::create([
            'company_id' => $this->seller->id,
            'user_id' => $this->sellerUser->id,
            'status' => Listing::STATUS_ACTIVE,
            'type' => Listing::TYPE_SUPPLY,
            'title' => 'Цемент М400 навалом, отгрузка с завода',
            'currency' => 'UZS',
        ]);
    }

    /** Покупателю — тариф с откликами (Business: 40 в месяц). */
    private function grantPlan(string $code = 'business'): void
    {
        app(SubscriptionService::class)->assign(
            $this->buyer,
            Plan::where('code', $code)->firstOrFail(),
            days: 30,
            source: Subscription::SOURCE_MANUAL,
            reason: 'Тест',
        );
    }

    private function respond(string $text = 'Здравствуйте! Интересует объём от 20 тонн.'): TestResponse
    {
        return $this->actingAs($this->buyerUser)
            ->post("/listing/{$this->listing->id}/respond", ['body' => $text]);
    }

    // ── Отклик ───────────────────────────────────────────────

    #[Test]
    public function отклик_создаёт_разговор_и_списывает_квоту(): void
    {
        $this->grantPlan();

        $this->respond()->assertRedirect()->assertSessionHasNoErrors();

        $thread = MessageThread::firstOrFail();

        $this->assertSame($this->buyer->id, $thread->buyer_company_id);
        $this->assertSame($this->seller->id, $thread->seller_company_id);
        $this->assertSame(1, $thread->messages()->count());
        $this->assertSame(1, (int) $this->buyer->wallet->fresh()->responses_used_this_period);
    }

    /**
     * Отклики открыты и на бесплатном тарифе — с месячным лимитом.
     * Закрытые отклики убивают ликвидность: закупщик, упёршийся
     * в оплату, уходит (аудит 29.08.2026, п. 4.8).
     */
    #[Test]
    public function бесплатный_тариф_откликается_в_пределах_лимита(): void
    {
        $this->respond()->assertSessionHasNoErrors();

        $this->assertSame(1, MessageThread::count());
    }

    #[Test]
    public function исчерпанный_лимит_бесплатного_тарифа_отклоняет_отклик(): void
    {
        $limit = (int) Plan::where('code', 'free')->value('responses_limit');
        Wallet::firstOrCreate(['company_id' => $this->buyer->id])
            ->forceFill(['responses_used_this_period' => $limit])->save();

        $this->respond()->assertSessionHasErrors('body');

        $this->assertSame(0, MessageThread::count());
    }

    #[Test]
    public function исчерпанный_лимит_отклоняет_отклик(): void
    {
        $this->grantPlan();

        $limit = (int) Plan::where('code', 'business')->value('responses_limit');
        Wallet::firstOrCreate(['company_id' => $this->buyer->id])
            ->forceFill(['responses_used_this_period' => $limit])->save();

        $this->respond()->assertSessionHasErrors('body');

        $this->assertSame(0, MessageThread::count());
    }

    /** Повторный отклик продолжает разговор и квоту второй раз не тратит. */
    #[Test]
    public function повторный_отклик_не_создаёт_второй_разговор(): void
    {
        $this->grantPlan();

        $this->respond('Первое сообщение');
        $this->respond('Второе сообщение');

        $this->assertSame(1, MessageThread::count());
        $this->assertSame(2, MessageThread::firstOrFail()->messages()->count());
        $this->assertSame(1, (int) $this->buyer->wallet->fresh()->responses_used_this_period);
    }

    #[Test]
    public function на_своё_объявление_откликнуться_нельзя(): void
    {
        $this->actingAs($this->sellerUser)
            ->post("/listing/{$this->listing->id}/respond", ['body' => 'Сам себе пишу'])
            ->assertSessionHasErrors('body');

        $this->assertSame(0, MessageThread::count());
    }

    #[Test]
    public function на_снятое_объявление_откликнуться_нельзя(): void
    {
        $this->grantPlan();
        $this->listing->forceFill(['status' => Listing::STATUS_ARCHIVED])->save();

        $this->respond()->assertSessionHasErrors('body');
    }

    /** Безлимитный тариф (VIP, responses_limit = null) откликается свободно. */
    #[Test]
    public function безлимитный_тариф_откликается_без_квоты(): void
    {
        $this->grantPlan('vip');

        $this->respond()->assertSessionHasNoErrors();

        $this->assertSame(1, MessageThread::count());
    }

    // ── Переписка ────────────────────────────────────────────

    #[Test]
    public function продавец_отвечает_в_разговоре(): void
    {
        $this->grantPlan();
        $this->respond();

        $thread = MessageThread::firstOrFail();

        $this->actingAs($this->sellerUser)
            ->post("/cabinet/chats/{$thread->id}", ['body' => 'Есть в наличии, отгрузим за два дня'])
            ->assertRedirect()
            ->assertSessionHasNoErrors();

        $this->assertSame(2, $thread->messages()->count());
    }

    #[Test]
    public function непрочитанное_считается_и_сбрасывается_открытием(): void
    {
        $this->grantPlan();
        $this->respond();

        $thread = MessageThread::firstOrFail();

        // У продавца одно непрочитанное — отклик покупателя
        $this->assertSame(1, $thread->unreadCountFor($this->seller));
        $this->assertSame(1, MessageThread::unreadThreadsFor($this->seller));

        // Открытие разговора помечает прочитанным
        $this->actingAs($this->sellerUser)->get("/cabinet/chats/{$thread->id}")->assertOk();

        $this->assertSame(0, $thread->fresh()->unreadCountFor($this->seller));
        $this->assertSame(0, MessageThread::unreadThreadsFor($this->seller));
    }

    #[Test]
    public function посторонняя_компания_не_видит_чужой_разговор(): void
    {
        $this->grantPlan();
        $this->respond();

        $thread = MessageThread::firstOrFail();

        $stranger = User::factory()->for(Company::factory()->create())->create(['email_verified_at' => now()]);

        $this->actingAs($stranger)->get("/cabinet/chats/{$thread->id}")->assertNotFound();
        $this->actingAs($stranger)
            ->post("/cabinet/chats/{$thread->id}", ['body' => 'Подглядываю'])
            ->assertNotFound();
    }

    #[Test]
    public function контакты_в_сообщении_маскируются(): void
    {
        $this->grantPlan();

        $this->respond('Звоните +998 90 123-45-67 или пишите sales@stroybaza.uz, сайт https://stroybaza.uz и телеграм @stroybaza');

        $body = MessageThread::firstOrFail()->messages()->firstOrFail()->body;

        $this->assertStringNotContainsString('123-45-67', $body);
        $this->assertStringNotContainsString('sales@stroybaza.uz', $body);
        $this->assertStringNotContainsString('https://', $body);
        $this->assertStringNotContainsString('@stroybaza', $body);
        $this->assertStringContainsString('[скрыто]', $body);
    }

    /** Цены маскировка не трогает: «1 200 000 сум» — не телефон. */
    #[Test]
    public function цены_не_маскируются(): void
    {
        $this->assertSame(
            'Готовы взять по 1 200 000 сум за тонну, объём 20 тонн',
            ChatService::maskContacts('Готовы взять по 1 200 000 сум за тонну, объём 20 тонн'),
        );
    }

    #[Test]
    public function получатель_уведомляется_о_первом_непрочитанном(): void
    {
        $this->grantPlan();

        $this->respond('Первое');
        $this->respond('Второе — уведомление не дублируется');

        $notifications = UserNotification::query()
            ->where('user_id', $this->sellerUser->id)
            ->where('type', 'chat')
            ->count();

        $this->assertSame(1, $notifications);
    }

    // ── Страницы кабинета ────────────────────────────────────

    #[Test]
    public function список_чатов_показывает_разговор_обеим_сторонам(): void
    {
        $this->grantPlan();
        $this->respond();

        $this->actingAs($this->buyerUser)->get('/cabinet/chats')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->component('cabinet/Chats')
                ->has('threads', 1)
                ->where('threads.0.company', $this->seller->name));

        $this->actingAs($this->sellerUser)->get('/cabinet/chats')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('threads', 1)
                ->where('threads.0.company', $this->buyer->name)
                ->where('threads.0.unread', 1));
    }

    #[Test]
    public function страница_разговора_отдаёт_сообщения(): void
    {
        $this->grantPlan();
        $this->respond('Интересует объём от 20 тонн');

        $thread = MessageThread::firstOrFail();

        $this->actingAs($this->buyerUser)->get("/cabinet/chats/{$thread->id}")
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->component('cabinet/Chat')
                ->has('messages', 1)
                ->where('messages.0.mine', true)
                ->where('thread.company', $this->seller->name));
    }
}
