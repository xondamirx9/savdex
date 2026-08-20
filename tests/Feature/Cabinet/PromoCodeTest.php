<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Exceptions\PromoCodeRejected;
use App\Models\Company;
use App\Models\Payment;
use App\Models\Plan;
use App\Models\PromoCode;
use App\Models\Subscription;
use App\Models\User;
use App\Services\PromoCodeService;
use App\Services\SubscriptionService;
use Database\Seeders\PlanSeeder;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Support\Facades\DB;
use Illuminate\Testing\TestResponse;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Промокод на бесплатный период тарифа.
 *
 * Акция для тех, кто ещё не платил: код выдаёт месяц Premium без счёта.
 * Проверяется вся дорога — от ввода в кабинете до подписки с кошельком,
 * и все отказы: погашенный код, просроченный, платившая компания.
 *
 * Цена ошибки здесь — раздача платного тарифа бесплатно, поэтому
 * повторное использование и гонка проверяются отдельно.
 */
class PromoCodeTest extends TestCase
{
    use RefreshDatabase;

    private User $user;

    private Company $company;

    protected function setUp(): void
    {
        parent::setUp();

        $this->seed(PlanSeeder::class);

        $this->company = Company::factory()->create();
        $this->user = User::factory()->for($this->company)->create(['email_verified_at' => now()]);
    }

    private function premium(): Plan
    {
        return Plan::where('code', 'premium')->firstOrFail();
    }

    private function code(array $overrides = []): PromoCode
    {
        return PromoCode::create(array_merge([
            'code' => PromoCode::generateCode(),
            'plan_id' => $this->premium()->id,
            'days' => 30,
            'is_active' => true,
        ], $overrides));
    }

    private function redeem(string $code): TestResponse
    {
        return $this->actingAs($this->user)->post('/cabinet/billing/promo', ['promo_code' => $code]);
    }

    // ── Активация ────────────────────────────────────────────

    #[Test]
    public function код_выдаёт_месяц_премиума(): void
    {
        $promo = $this->code();

        $this->redeem($promo->code)->assertRedirect()->assertSessionHasNoErrors();

        $subscription = $this->company->fresh()->subscription;

        $this->assertNotNull($subscription);
        $this->assertSame($this->premium()->id, $subscription->plan_id);
        $this->assertSame(Subscription::SOURCE_PROMO, $subscription->source);
        $this->assertSame(30, (int) $subscription->started_at->diffInDays($subscription->ends_at));
    }

    /** Подарочный месяц не должен продлеваться счётом: акция разовая. */
    #[Test]
    public function подписка_по_промокоду_не_продлевается(): void
    {
        $this->redeem($this->code()->code);

        $this->assertFalse((bool) $this->company->fresh()->subscription->auto_renew);
    }

    /** Лимиты тарифа приходят вместе с подпиской — иначе доступ пустой. */
    #[Test]
    public function промокод_наполняет_кошелёк_по_тарифу(): void
    {
        $this->redeem($this->code()->code);

        $wallet = $this->company->fresh()->wallet;

        $this->assertNotNull($wallet);
        $this->assertSame($this->premium()->promo_units, $wallet->promo_units);
        $this->assertSame(0, $wallet->contacts_used_this_period);
    }

    #[Test]
    public function активация_записывается_в_код(): void
    {
        $promo = $this->code();

        $this->redeem($promo->code);

        $promo->refresh();

        $this->assertNotNull($promo->used_at);
        $this->assertSame($this->company->id, $promo->used_by_company_id);
        $this->assertSame($this->user->id, $promo->used_by_user_id);
        $this->assertSame($this->company->fresh()->subscription->id, $promo->subscription_id);
    }

    /** Код диктуют по телефону: регистр и пробелы не должны мешать. */
    #[Test]
    public function код_принимается_в_любом_регистре_и_с_пробелами(): void
    {
        $promo = $this->code(['code' => 'SVDX-ABCD2345']);

        $this->redeem(' svdx-abcd 2345 ')->assertSessionHasNoErrors();

        $this->assertNotNull($promo->fresh()->used_at);
    }

    // ── Отказы ───────────────────────────────────────────────

    #[Test]
    public function несуществующий_код_отклоняется(): void
    {
        $this->redeem('SVDX-NOSUCH01')->assertSessionHasErrors('promo_code');

        $this->assertNull($this->company->fresh()->subscription);
    }

    #[Test]
    public function погашенный_код_второй_раз_не_срабатывает(): void
    {
        $promo = $this->code();
        $this->redeem($promo->code)->assertSessionHasNoErrors();

        // Вторая компания с тем же кодом
        $other = Company::factory()->create();
        $otherUser = User::factory()->for($other)->create(['email_verified_at' => now()]);

        $this->actingAs($otherUser)
            ->post('/cabinet/billing/promo', ['promo_code' => $promo->code])
            ->assertSessionHasErrors('promo_code');

        $this->assertNull($other->fresh()->subscription);
    }

    #[Test]
    public function просроченный_код_отклоняется(): void
    {
        $promo = $this->code(['expires_at' => now()->subDay()]);

        $this->redeem($promo->code)->assertSessionHasErrors('promo_code');

        $this->assertNull($promo->fresh()->used_at);
    }

    #[Test]
    public function отключённый_код_отклоняется(): void
    {
        $promo = $this->code(['is_active' => false]);

        $this->redeem($promo->code)->assertSessionHasErrors('promo_code');
    }

    /** Акция — знакомство с платным тарифом, а не способ не платить дальше. */
    #[Test]
    public function платившая_компания_промокод_не_активирует(): void
    {
        Payment::create([
            'company_id' => $this->company->id,
            'number' => 'SVD-000777',
            'purpose' => 'subscription',
            'description' => 'Тариф',
            'amount' => 100000,
            'currency' => 'UZS',
            'provider' => 'invoice',
            'status' => 'paid',
            'paid_at' => now(),
        ]);

        $this->redeem($this->code()->code)->assertSessionHas('error');

        $this->assertNull($this->company->fresh()->subscription);
    }

    #[Test]
    public function вторая_попытка_по_другому_коду_отклоняется(): void
    {
        $this->redeem($this->code()->code)->assertSessionHasNoErrors();

        // Подписка кончилась, компания пробует второй код
        $this->company->fresh()->subscription->forceFill([
            'status' => 'expired',
            'ends_at' => now()->subDay(),
        ])->save();

        $this->redeem($this->code()->code)->assertSessionHas('error');
    }

    /** Действующий тариф нельзя молча заменить подарочным. */
    #[Test]
    public function при_действующем_тарифе_код_отклоняется(): void
    {
        app(SubscriptionService::class)->assign(
            $this->company,
            $this->premium(),
            days: 30,
            source: Subscription::SOURCE_MANUAL,
            reason: 'Тест',
        );

        $this->redeem($this->code()->code)->assertSessionHas('error');
    }

    #[Test]
    public function без_компании_код_не_активируется(): void
    {
        $lonely = User::factory()->create(['email_verified_at' => now(), 'company_id' => null]);

        $this->actingAs($lonely)
            ->post('/cabinet/billing/promo', ['promo_code' => $this->code()->code])
            ->assertSessionHasErrors('promo_code');
    }

    #[Test]
    public function неподтверждённая_почта_не_пропускается(): void
    {
        $this->user->forceFill(['email_verified_at' => null])->save();

        $this->redeem($this->code()->code)->assertRedirect('/verify-email');
    }

    /** Возврат денег — тоже оплата в прошлом, акция уже не действует. */
    #[Test]
    public function компания_с_возвращённым_платежом_код_не_активирует(): void
    {
        Payment::create([
            'company_id' => $this->company->id,
            'number' => 'SVD-000778',
            'purpose' => 'subscription',
            'description' => 'Тариф',
            'amount' => 100000,
            'currency' => 'UZS',
            'provider' => 'invoice',
            'status' => 'refunded',
        ]);

        $this->redeem($this->code()->code)->assertSessionHas('error');
    }

    /** Код с нулевым сроком выдал бы бессрочный бесплатный тариф. */
    #[Test]
    public function код_с_нулевым_сроком_отклоняется(): void
    {
        $promo = $this->code(['days' => 0]);

        $this->redeem($promo->code)->assertSessionHasErrors('promo_code');

        $this->assertNull($this->company->fresh()->subscription);
    }

    /**
     * Гонка: код погашен между чтением и записью.
     *
     * Захват идёт условным UPDATE, поэтому второй запрос получает ноль
     * изменённых строк — на SQLite, где lockForUpdate ничего не блокирует,
     * это единственная работающая защита.
     */
    #[Test]
    public function код_погашенный_между_проверкой_и_записью_не_срабатывает(): void
    {
        $promo = $this->code();
        $other = Company::factory()->create();

        DB::transaction(function () use ($promo, $other): void {
            // Имитируем конкурента, успевшего захватить код первым
            PromoCode::query()->where('id', $promo->id)->update([
                'used_at' => now(),
                'used_by_company_id' => $other->id,
            ]);
        });

        $this->redeem($promo->code)->assertSessionHasErrors('promo_code');

        $this->assertNull($this->company->fresh()->subscription);
    }

    // ── Окончание бесплатного месяца ─────────────────────────

    /**
     * Доступ обязан кончиться сам, без планировщика: на хостинге cron
     * может быть не заведён, и тогда подарочный месяц стал бы вечным.
     */
    #[Test]
    public function истёкшая_подписка_не_даёт_доступ_без_планировщика(): void
    {
        $this->redeem($this->code()->code)->assertSessionHasNoErrors();

        $company = $this->company->fresh();
        $this->assertSame('Premium', $company->plan()->name);

        // Срок вышел, но плановая команда ещё не отработала
        Subscription::query()->where('company_id', $company->id)
            ->update(['ends_at' => now()->subDay()]);

        $this->assertSame(Plan::FREE, $company->fresh()->plan()->code);
    }

    /** Подарочную подписку нельзя «возобновить»: счёт выставлять не за что. */
    #[Test]
    public function автопродление_подарочной_подписки_не_включается(): void
    {
        $this->redeem($this->code()->code);

        // Свежий пользователь: объект из setUp держит отношения,
        // загруженные до активации, и подписки в них ещё нет
        $this->actingAs($this->user->fresh())->post('/cabinet/billing/resume')->assertRedirect();

        $this->assertFalse((bool) $this->company->fresh()->subscription->auto_renew);
    }

    // ── Форма в кабинете ─────────────────────────────────────

    #[Test]
    public function форма_промокода_видна_только_подходящей_компании(): void
    {
        $this->actingAs($this->user)->get('/cabinet/billing')
            ->assertInertia(fn (AssertableInertia $page) => $page->where('promoAllowed', true));

        $this->redeem($this->code()->code);

        $this->actingAs($this->user)->get('/cabinet/billing')
            ->assertInertia(fn (AssertableInertia $page) => $page->where('promoAllowed', false));
    }

    // ── Сервис ───────────────────────────────────────────────

    #[Test]
    public function пустой_код_отклоняется_сервисом(): void
    {
        $this->expectException(PromoCodeRejected::class);

        app(PromoCodeService::class)->redeem('   ', $this->company, $this->user);
    }

    /** Выпуск кодов не должен давать одинаковых: код именной. */
    #[Test]
    public function сгенерированные_коды_не_повторяются(): void
    {
        $codes = collect(range(1, 200))->map(fn (): string => PromoCode::generateCode());

        $this->assertCount(200, $codes->unique());
    }

    /** В алфавите нет знаков, которые путают при наборе с листовки. */
    #[Test]
    public function в_коде_нет_похожих_знаков(): void
    {
        $code = PromoCode::generateCode('SVDX');

        $this->assertDoesNotMatchRegularExpression('/[01OIL]/', substr($code, 5));
    }
}
