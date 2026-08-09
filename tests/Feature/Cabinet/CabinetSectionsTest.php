<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\Company;
use App\Models\ContactUnlock;
use App\Models\Listing;
use App\Models\Plan;
use App\Models\PromotionType;
use App\Models\Review;
use App\Models\Subscription;
use App\Models\User;
use App\Models\Wallet;
use Database\Seeders\PlanSeeder;
use Database\Seeders\PromotionTypeSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Разделы кабинета: объявления, контакты, продвижение, отзывы, биллинг.
 *
 * Проверяется не только «страница открылась», но и правила, на которых
 * держится монетизация: чужое не редактируется, лимиты не обходятся,
 * кредиты не уходят в минус.
 */
class CabinetSectionsTest extends TestCase
{
    use RefreshDatabase;

    private User $user;

    private Company $company;

    protected function setUp(): void
    {
        parent::setUp();

        $this->seed(PlanSeeder::class);

        $this->company = Company::factory()->create();
        $this->user = User::factory()->for($this->company)->create();

        Wallet::create([
            'company_id' => $this->company->id,
            'credits' => 5,
            'promo_units' => 10,
        ]);
    }

    private function listing(array $overrides = []): Listing
    {
        return Listing::factory()->create([
            'company_id' => $this->company->id,
            'status' => Listing::STATUS_ACTIVE,
            ...$overrides,
        ]);
    }

    // ── Объявления ───────────────────────────────────────────

    #[Test]
    public function список_объявлений_фильтруется_по_статусу(): void
    {
        $this->listing(['title' => 'Активное объявление']);
        $this->listing(['title' => 'Черновик', 'status' => Listing::STATUS_DRAFT]);

        $this->actingAs($this->user)
            ->get('/cabinet/listings?status=draft')
            ->assertInertia(fn (AssertableInertia $p) => $p
                ->where('status', 'draft')
                ->has('listings', 1)
                ->where('listings.0.title', 'Черновик')
                ->where('counts.active', 1),
            );
    }

    #[Test]
    public function продление_сдвигает_срок_от_текущего_момента(): void
    {
        // Просроченное на месяц: отсчёт от даты истечения оставил бы
        // объявление снова истёкшим
        $listing = $this->listing([
            'status' => Listing::STATUS_EXPIRED,
            'expires_at' => now()->subMonth(),
        ]);

        $this->actingAs($this->user)->post("/cabinet/listings/{$listing->id}/renew");

        $listing->refresh();

        $this->assertSame(Listing::STATUS_ACTIVE, $listing->status);
        $this->assertTrue($listing->expires_at->isFuture());
    }

    #[Test]
    public function чужое_объявление_не_продлевается(): void
    {
        $foreign = Listing::factory()->create(['company_id' => Company::factory()->create()->id]);

        $this->actingAs($this->user)
            ->post("/cabinet/listings/{$foreign->id}/renew")
            ->assertNotFound();
    }

    #[Test]
    public function массовое_действие_не_трогает_чужие_объявления(): void
    {
        $mine = $this->listing();
        $foreign = Listing::factory()->create([
            'company_id' => Company::factory()->create()->id,
            'status' => Listing::STATUS_ACTIVE,
        ]);

        $this->actingAs($this->user)->post('/cabinet/listings/bulk', [
            'action' => 'archive',
            'ids' => [$mine->id, $foreign->id],
        ]);

        $this->assertSame(Listing::STATUS_ARCHIVED, $mine->fresh()->status);
        $this->assertSame(Listing::STATUS_ACTIVE, $foreign->fresh()->status, 'Чужое объявление не должно меняться');
    }

    #[Test]
    public function лимит_тарифа_не_даёт_создать_лишнее_объявление(): void
    {
        // Free разрешает 4 активных
        Listing::factory()->count(4)->create([
            'company_id' => $this->company->id,
            'status' => Listing::STATUS_ACTIVE,
        ]);

        $this->actingAs($this->user)
            ->get('/cabinet/listings/create')
            ->assertRedirect('/cabinet/listings')
            ->assertSessionHas('error');
    }

    #[Test]
    public function черновик_не_занимает_слот_тарифа(): void
    {
        Listing::factory()->count(4)->create([
            'company_id' => $this->company->id,
            'status' => Listing::STATUS_DRAFT,
        ]);

        $this->actingAs($this->user)->get('/cabinet/listings/create')->assertRedirectContains('/edit');
    }

    #[Test]
    public function публикация_требует_заполненных_полей(): void
    {
        $draft = $this->listing(['status' => Listing::STATUS_DRAFT, 'title' => '']);

        $this->actingAs($this->user)
            ->post("/cabinet/listings/{$draft->id}/publish", ['title' => 'Коротко'])
            ->assertSessionHasErrors(['category_id', 'title', 'description']);

        $this->assertSame(Listing::STATUS_DRAFT, $draft->fresh()->status);
    }

    // ── Контакты ─────────────────────────────────────────────

    #[Test]
    public function мои_контакты_показывают_только_свои_раскрытия(): void
    {
        $target = Company::factory()->create();
        ContactUnlock::factory()->create([
            'company_id' => $this->company->id,
            'target_company_id' => $target->id,
        ]);

        // Чужое раскрытие между двумя другими компаниями
        ContactUnlock::factory()->create([
            'company_id' => Company::factory()->create()->id,
            'target_company_id' => Company::factory()->create()->id,
        ]);

        $this->actingAs($this->user)
            ->get('/cabinet/contacts')
            ->assertInertia(fn (AssertableInertia $p) => $p->has('contacts', 1));
    }

    #[Test]
    public function жалоба_не_отправляется_дважды(): void
    {
        $unlock = ContactUnlock::factory()->create([
            'company_id' => $this->company->id,
            'target_company_id' => Company::factory()->create()->id,
        ]);

        $payload = ['reason' => 'Номер не отвечает третий день подряд'];

        $this->actingAs($this->user)->post("/cabinet/contacts/{$unlock->id}/complaint", $payload);
        $this->actingAs($this->user)
            ->post("/cabinet/contacts/{$unlock->id}/complaint", $payload)
            ->assertSessionHas('error');

        $this->assertSame('pending', $unlock->fresh()->complaint_status);
    }

    #[Test]
    public function выгрузка_контактов_отдаёт_csv(): void
    {
        ContactUnlock::factory()->create([
            'company_id' => $this->company->id,
            'target_company_id' => Company::factory()->create()->id,
        ]);

        $this->actingAs($this->user)
            ->get('/cabinet/contacts/export')
            ->assertOk()
            ->assertHeader('content-type', 'text/csv; charset=UTF-8');
    }

    // ── Кто мной интересуется ────────────────────────────────

    #[Test]
    public function имена_интересующихся_скрыты_на_младшем_тарифе(): void
    {
        ContactUnlock::factory()->create([
            'company_id' => Company::factory()->create(['name' => 'ООО «Тайный покупатель»'])->id,
            'target_company_id' => $this->company->id,
        ]);

        // Скрытие должно происходить на сервере: отдать имя и спрятать
        // его в вёрстке значит отдать его совсем
        $this->actingAs($this->user)
            ->get('/cabinet/incoming')
            ->assertInertia(fn (AssertableInertia $p) => $p
                ->where('sees_names', false)
                ->where('rows.0.name', null),
            )
            ->assertDontSee('Тайный покупатель');
    }

    #[Test]
    public function имена_видны_на_business(): void
    {
        Subscription::create([
            'company_id' => $this->company->id,
            'plan_id' => Plan::where('code', 'business')->value('id'),
            'status' => 'active',
            'started_at' => now(),
            'ends_at' => now()->addMonth(),
        ]);

        ContactUnlock::factory()->create([
            'company_id' => Company::factory()->create(['name' => 'ООО «Покупатель»'])->id,
            'target_company_id' => $this->company->id,
        ]);

        $this->actingAs($this->user)
            ->get('/cabinet/incoming')
            ->assertInertia(fn (AssertableInertia $p) => $p
                ->where('sees_names', true)
                ->where('rows.0.name', 'ООО «Покупатель»'),
            );
    }

    // ── Продвижение ──────────────────────────────────────────

    #[Test]
    public function продвижение_списывает_единицы(): void
    {
        $this->seed(PromotionTypeSeeder::class);

        $listing = $this->listing();
        $type = PromotionType::where('code', 'bump')->firstOrFail();

        $this->actingAs($this->user)->post('/cabinet/promo', [
            'listing_id' => $listing->id,
            'promotion_type_id' => $type->id,
        ])->assertSessionHas('success');

        $this->assertSame(10 - $type->cost_units, $this->company->wallet->fresh()->promo_units);
        $this->assertDatabaseHas('promotions', ['listing_id' => $listing->id, 'status' => 'active']);

        // Списание обязано попасть в историю: остаток должен быть
        // выводим из неё, иначе спор о балансе нечем закрыть
        $this->assertDatabaseHas('wallet_transactions', [
            'company_id' => $this->company->id,
            'kind' => 'promo_units',
            'amount' => -$type->cost_units,
            'reason' => 'promotion',
        ]);
    }

    #[Test]
    public function продвижение_не_запускается_без_единиц(): void
    {
        $this->seed(PromotionTypeSeeder::class);

        $this->company->wallet->update(['promo_units' => 0]);
        $listing = $this->listing();

        $this->actingAs($this->user)->post('/cabinet/promo', [
            'listing_id' => $listing->id,
            'promotion_type_id' => PromotionType::where('code', 'bump')->value('id'),
        ])->assertSessionHas('error');

        $this->assertDatabaseCount('promotions', 0);
    }

    #[Test]
    public function одно_и_то_же_продвижение_не_дублируется(): void
    {
        $this->seed(PromotionTypeSeeder::class);

        $listing = $this->listing();
        $typeId = PromotionType::where('code', 'bump')->value('id');

        $payload = ['listing_id' => $listing->id, 'promotion_type_id' => $typeId];

        $this->actingAs($this->user)->post('/cabinet/promo', $payload);
        $this->actingAs($this->user)->post('/cabinet/promo', $payload)->assertSessionHas('error');

        $this->assertDatabaseCount('promotions', 1);
    }

    // ── Отзывы ───────────────────────────────────────────────

    #[Test]
    public function ответ_на_отзыв_сохраняется(): void
    {
        $review = Review::factory()->create([
            'company_id' => $this->company->id,
            'author_company_id' => Company::factory()->create()->id,
        ]);

        $this->actingAs($this->user)->post("/cabinet/reviews/{$review->id}/reply", [
            'reply' => 'Спасибо за отзыв, учли замечание по срокам',
        ])->assertSessionHas('success');

        $this->assertNotNull($review->fresh()->reply);
    }

    /**
     * Распределение оценок обязано приходить списком от 5 к 1.
     *
     * Объект с числовыми ключами {«5»:1,«4»:0} JavaScript пересортирует
     * по возрастанию, и шкала перевернётся — единицы окажутся сверху.
     * В коде это не видно: порядок теряется при сериализации.
     */
    #[Test]
    public function распределение_оценок_идёт_от_пяти_к_одной(): void
    {
        Review::factory()->create([
            'company_id' => $this->company->id,
            'author_company_id' => Company::factory()->create()->id,
            'rating' => 5,
        ]);

        $this->actingAs($this->user)
            ->get('/cabinet/reviews')
            ->assertInertia(fn (AssertableInertia $p) => $p
                ->where('summary.distribution.0.star', 5)
                ->where('summary.distribution.0.count', 1)
                ->where('summary.distribution.4.star', 1),
            );
    }

    #[Test]
    public function чужой_отзыв_не_комментируется(): void
    {
        $foreign = Review::factory()->create([
            'company_id' => Company::factory()->create()->id,
            'author_company_id' => Company::factory()->create()->id,
        ]);

        $this->actingAs($this->user)
            ->post("/cabinet/reviews/{$foreign->id}/reply", ['reply' => 'Чужой ответ на чужой отзыв'])
            ->assertNotFound();
    }

    // ── Биллинг и настройки ──────────────────────────────────

    #[Test]
    public function отмена_автопродления_сохраняет_оплаченный_период(): void
    {
        $subscription = Subscription::create([
            'company_id' => $this->company->id,
            'plan_id' => Plan::where('code', 'business')->value('id'),
            'status' => 'active',
            'started_at' => now(),
            'ends_at' => now()->addMonth(),
            'auto_renew' => true,
        ]);

        $this->actingAs($this->user)->post('/cabinet/billing/cancel')->assertSessionHas('success');

        $subscription->refresh();

        $this->assertFalse($subscription->auto_renew);
        $this->assertSame('active', $subscription->status, 'Оплаченный период не должен обрываться');
    }

    #[Test]
    public function настройки_уведомлений_сохраняются(): void
    {
        $this->actingAs($this->user)->patch('/cabinet/settings/notifications', [
            'notifications' => [
                ['event' => 'new_review', 'email' => false, 'telegram' => true],
            ],
        ])->assertSessionHas('success');

        $this->assertDatabaseHas('notification_preferences', [
            'user_id' => $this->user->id,
            'event' => 'new_review',
            'email' => false,
            'telegram' => true,
        ]);
    }

    #[Test]
    public function удаление_аккаунта_требует_пароль(): void
    {
        $this->actingAs($this->user)
            ->post('/cabinet/settings/delete', ['password' => 'ne-tot-parol'])
            ->assertSessionHasErrors('password');

        $this->assertNotSoftDeleted('users', ['id' => $this->user->id]);
    }
}
