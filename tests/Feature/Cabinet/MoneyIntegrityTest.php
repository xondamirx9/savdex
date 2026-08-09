<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\Company;
use App\Models\CompanyContact;
use App\Models\ContactUnlock;
use App\Models\Listing;
use App\Models\Plan;
use App\Models\Promotion;
use App\Models\PromotionType;
use App\Models\Subscription;
use App\Models\User;
use App\Models\Wallet;
use App\Services\ContactUnlockService;
use Illuminate\Database\UniqueConstraintViolationException;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Целостность денежных операций.
 *
 * Обещания площадки — «лимит тарифа столько-то», «одно продвижение
 * на объявление» — должны держаться базой, а не только проверкой в коде.
 * Между проверкой и записью помещается второй запрос, и там, где
 * опоры в схеме нет, обещание нарушается молча.
 */
class MoneyIntegrityTest extends TestCase
{
    use RefreshDatabase;

    private User $user;

    private Company $company;

    protected function setUp(): void
    {
        parent::setUp();

        $this->company = Company::factory()->create();
        $this->user = User::factory()->for($this->company)->create(['email_verified_at' => now()]);
    }

    private function plan(int $contactsLimit): Plan
    {
        $plan = Plan::create([
            'code' => 'test', 'name' => 'Test', 'price_usd' => 0, 'period_days' => 30,
            'listing_days' => 30, 'listings_limit' => 10, 'contacts_limit' => $contactsLimit,
            'promo_units' => 0, 'verification_days' => 3,
        ]);

        Subscription::create([
            'company_id' => $this->company->id,
            'plan_id' => $plan->id,
            'status' => 'active',
            'started_at' => now(),
            'ends_at' => now()->addDays(30),
        ]);

        return $plan;
    }

    private function supplier(): Company
    {
        $supplier = Company::factory()->create();

        CompanyContact::create([
            'company_id' => $supplier->id,
            'type' => 'phone',
            'value' => '+998 90 123-45-67',
            'is_public' => true,
        ]);

        return $supplier;
    }

    /**
     * Лимит тарифа не перешагивается.
     *
     * Раньше остаток читался до транзакции и без блокировки строки:
     * два раскрытия на последнем слоте оба видели свободное место.
     */
    #[Test]
    public function лимит_тарифа_не_превышается(): void
    {
        $this->plan(contactsLimit: 2);
        Wallet::create(['company_id' => $this->company->id, 'credits' => 0]);

        $service = app(ContactUnlockService::class);

        foreach (range(1, 3) as $i) {
            $result = $service->unlock($this->user->fresh(), $this->supplier());

            $expected = $i <= 2;
            $this->assertSame($expected, $result['ok'], "Раскрытие №{$i}");
        }

        $wallet = $this->company->fresh()->wallet;

        $this->assertSame(2, $wallet->contacts_used_this_period, 'израсходовано ровно столько, сколько даёт тариф');
        $this->assertSame(0, $wallet->credits);
        $this->assertSame(2, ContactUnlock::where('company_id', $this->company->id)->count());
    }

    /** Сверх лимита списываются кредиты, а не выдаётся отказ. */
    #[Test]
    public function сверх_лимита_идут_кредиты(): void
    {
        $this->plan(contactsLimit: 1);
        Wallet::create(['company_id' => $this->company->id, 'credits' => 1]);

        $service = app(ContactUnlockService::class);

        $this->assertTrue($service->unlock($this->user->fresh(), $this->supplier())['ok']);
        $this->assertTrue($service->unlock($this->user->fresh(), $this->supplier())['ok']);
        $this->assertFalse($service->unlock($this->user->fresh(), $this->supplier())['ok']);

        $wallet = $this->company->fresh()->wallet;

        $this->assertSame(1, $wallet->contacts_used_this_period);
        $this->assertSame(0, $wallet->credits);
    }

    /** Расход кредита остаётся в журнале движений. */
    #[Test]
    public function списание_кредита_попадает_в_журнал(): void
    {
        $this->plan(contactsLimit: 0);
        Wallet::create(['company_id' => $this->company->id, 'credits' => 1]);

        app(ContactUnlockService::class)->unlock($this->user->fresh(), $this->supplier());

        $this->assertDatabaseHas('wallet_transactions', [
            'company_id' => $this->company->id,
            'kind' => 'credits',
            'amount' => -1,
            'reason' => 'unlock',
        ]);
    }

    // ── Продвижение ──────────────────────────────────────────

    private function promotionType(int $cost = 1): PromotionType
    {
        return PromotionType::create([
            'code' => 'bump', 'name' => 'Поднять', 'cost_units' => $cost,
            'duration_days' => 7, 'is_active' => true,
            'description' => 'Объявление поднимается в начало выдачи',
        ]);
    }

    /**
     * Второе такое же продвижение не запускается даже в обход проверки
     * в контроллере: обещание держит уникальный индекс.
     */
    #[Test]
    public function повторное_продвижение_отклоняется_базой(): void
    {
        $type = $this->promotionType();
        $listing = Listing::factory()->create(['company_id' => $this->company->id]);

        $row = [
            'listing_id' => $listing->id,
            'company_id' => $this->company->id,
            'promotion_type_id' => $type->id,
            'units_spent' => 1,
            'status' => 'active',
            'starts_at' => now(),
            'ends_at' => now()->addDays(7),
            'impressions_before' => 0,
        ];

        Promotion::create($row);

        $this->expectException(UniqueConstraintViolationException::class);

        Promotion::create($row);
    }

    /** Завершённое продвижение освобождает место — иначе оно занято навсегда. */
    #[Test]
    public function завершённое_продвижение_освобождает_место(): void
    {
        $type = $this->promotionType();
        $listing = Listing::factory()->create(['company_id' => $this->company->id]);

        $row = [
            'listing_id' => $listing->id,
            'company_id' => $this->company->id,
            'promotion_type_id' => $type->id,
            'units_spent' => 1,
            'status' => 'active',
            'starts_at' => now(),
            'ends_at' => now()->subDay(),
            'impressions_before' => 0,
        ];

        $first = Promotion::create($row);

        $this->artisan('promotions:finish')->assertSuccessful();

        $this->assertSame('finished', $first->fresh()->status);
        $this->assertNull($first->fresh()->active_key);

        Promotion::create([...$row, 'ends_at' => now()->addDays(7)]);

        $this->assertSame(2, Promotion::where('listing_id', $listing->id)->count());
    }

    /**
     * Если запуск не удался, единицы возвращаются: списание и создание
     * идут одной транзакцией. Раньше spend() коммитился отдельно,
     * и падение оставляло компанию без единиц и без продвижения.
     */
    #[Test]
    public function неудачный_запуск_не_списывает_единицы(): void
    {
        $type = $this->promotionType(cost: 3);
        $listing = Listing::factory()->create([
            'company_id' => $this->company->id,
            'status' => Listing::STATUS_ACTIVE,
        ]);

        Wallet::create(['company_id' => $this->company->id, 'promo_units' => 10]);

        // Место уже занято этим же продвижением — вставка упрётся в индекс
        Promotion::create([
            'listing_id' => $listing->id,
            'company_id' => $this->company->id,
            'promotion_type_id' => $type->id,
            'units_spent' => 3,
            'status' => 'active',
            'starts_at' => now(),
            'ends_at' => now()->addDays(7),
            'impressions_before' => 0,
        ]);

        $this->actingAs($this->user)
            ->post('/cabinet/promo', ['listing_id' => $listing->id, 'promotion_type_id' => $type->id])
            ->assertSessionHas('error');

        $this->assertSame(10, $this->company->fresh()->wallet->promo_units, 'единицы должны остаться на счету');
    }
}
