<?php

declare(strict_types=1);

namespace Tests\Feature;

use App\Models\Company;
use App\Models\CompanyContact;
use App\Models\ContactUnlock;
use App\Models\Listing;
use App\Models\Plan;
use App\Models\User;
use App\Models\Wallet;
use App\Models\WalletTransaction;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Illuminate\Testing\TestResponse;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Покупка раскрытия контактов — операция, ради которой существует
 * вся схема кошелька, тарифов и лимитов.
 *
 * До этого раскрытия создавались только сидерами: маршрута не было,
 * кредиты не списывались нигде. Все тесты «оплаченный контакт виден»
 * проверяли вторую половину механики, первой из которых не существовало.
 */
class ContactUnlockPurchaseTest extends TestCase
{
    use RefreshDatabase;

    private Company $buyer;

    private User $user;

    private Company $supplier;

    private Wallet $wallet;

    protected function setUp(): void
    {
        parent::setUp();

        Plan::create([
            'code' => 'free',
            'name' => 'Free',
            'price_usd' => 0,
            'listings_limit' => 4,
            'listing_days' => 30,
            'contacts_limit' => 2,
            'promo_units' => 0,
            'period_days' => 30,
        ]);

        $this->buyer = Company::factory()->create(['name' => 'ООО «Покупатель»']);
        $this->user = User::factory()->create(['company_id' => $this->buyer->id]);

        $this->wallet = Wallet::create([
            'company_id' => $this->buyer->id,
            'credits' => 0,
            'promo_units' => 0,
            'contacts_used_this_period' => 0,
            'period_resets_at' => now()->addDays(30),
        ]);

        $this->supplier = Company::factory()->create(['name' => 'ООО «Поставщик»']);

        CompanyContact::create([
            'company_id' => $this->supplier->id,
            'type' => 'phone',
            'value' => '+998 90 555-11-22',
            'is_public' => true,
            'is_primary' => true,
        ]);
    }

    private function unlock(array $payload = []): TestResponse
    {
        return $this->actingAs($this->user)
            ->post("/company/{$this->supplier->slug}/unlock", $payload);
    }

    #[Test]
    public function первое_раскрытие_расходует_лимит_тарифа(): void
    {
        $this->unlock()->assertSessionHas('success');

        $unlock = ContactUnlock::first();

        $this->assertNotNull($unlock);
        $this->assertSame($this->buyer->id, $unlock->company_id);
        $this->assertSame($this->supplier->id, $unlock->target_company_id);

        // Пока лимит тарифа не исчерпан, кредиты не тратятся
        $this->assertSame(0, $unlock->credits_spent);
        $this->assertSame(1, $this->wallet->fresh()->contacts_used_this_period);
        $this->assertSame(0, $this->wallet->fresh()->credits);
    }

    #[Test]
    public function после_раскрытия_контакт_виден_целиком(): void
    {
        $this->unlock();

        $this->actingAs($this->user)
            ->get("/company/{$this->supplier->slug}")
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('unlocked', true)
                ->where('contacts.0.value', '+998 90 555-11-22')
                ->where('locked_count', 0),
            );
    }

    /**
     * Обещание витрины: заплатили один раз — доступ навсегда.
     * Повторное нажатие не должно списывать ничего.
     */
    #[Test]
    public function повторное_раскрытие_ничего_не_списывает(): void
    {
        $this->unlock();
        $this->unlock()->assertSessionHas('success');

        $this->assertSame(1, ContactUnlock::count());
        $this->assertSame(1, $this->wallet->fresh()->contacts_used_this_period);
    }

    /**
     * Сначала расходуется оплаченный подпиской лимит, и только
     * потом кредиты — иначе купленные кредиты сгорают при
     * неиспользованном лимите.
     */
    #[Test]
    public function после_лимита_тарифа_списывается_кредит(): void
    {
        $this->wallet->forceFill(['contacts_used_this_period' => 2, 'credits' => 3])->save();

        $this->unlock()->assertSessionHas('success');

        $this->assertSame(1, ContactUnlock::first()->credits_spent);
        $this->assertSame(2, $this->wallet->fresh()->credits);

        $transaction = WalletTransaction::where('reason', 'unlock')->first();

        $this->assertNotNull($transaction, 'Списание обязано попасть в историю кошелька');
        $this->assertSame(-1, $transaction->amount);
        $this->assertSame(2, $transaction->balance_after);
    }

    #[Test]
    public function без_лимита_и_кредитов_раскрытие_отклоняется(): void
    {
        $this->wallet->forceFill(['contacts_used_this_period' => 2, 'credits' => 0])->save();

        $this->unlock()->assertSessionHas('error');

        $this->assertSame(0, ContactUnlock::count());
        $this->assertSame(0, $this->wallet->fresh()->credits);
    }

    #[Test]
    public function свои_контакты_не_покупаются(): void
    {
        $own = User::factory()->create(['company_id' => $this->supplier->id]);

        $this->actingAs($own)
            ->post("/company/{$this->supplier->slug}/unlock")
            ->assertSessionHas('error');

        $this->assertSame(0, ContactUnlock::count());
    }

    #[Test]
    public function без_подтверждённой_почты_раскрытие_недоступно(): void
    {
        $unverified = User::factory()->unverified()->create(['company_id' => $this->buyer->id]);

        $this->actingAs($unverified)
            ->post("/company/{$this->supplier->slug}/unlock")
            ->assertRedirect('/verify-email');

        $this->assertSame(0, ContactUnlock::count());
    }

    #[Test]
    public function гость_на_раскрытие_не_попадает(): void
    {
        $this->post("/company/{$this->supplier->slug}/unlock")->assertRedirect('/login');
    }

    #[Test]
    public function владельцу_приходит_уведомление_о_раскрытии(): void
    {
        $owner = User::factory()->create(['company_id' => $this->supplier->id]);

        $this->unlock();

        $this->assertSame(1, $owner->alerts()->count());
        $this->assertSame(1, $this->supplier->events()->count());
    }

    /** Раскрытие по объявлению отмечает, откуда пришёл интерес. */
    #[Test]
    public function раскрытие_по_объявлению_учитывает_объявление(): void
    {
        // Счётчик задаётся явно: фабрика ставит случайное значение,
        // и проверять абсолют было бы проверкой фабрики, а не кода
        $listing = Listing::factory()->create([
            'company_id' => $this->supplier->id,
            'status' => Listing::STATUS_ACTIVE,
            'unlocks_count' => 0,
        ]);

        $this->unlock(['listing_id' => $listing->id]);

        $this->assertSame($listing->id, ContactUnlock::first()->listing_id);
        // Счётчик раскрытий объявления — основа конверсии в аналитике
        $this->assertSame(1, $listing->fresh()->unlocks_count);
        $this->assertSame(1, $listing->stats()->whereDate('date', today())->value('unlocks'));
    }

    /**
     * Чужое объявление в запросе не должно ни ломать раскрытие,
     * ни привязываться к нему.
     */
    #[Test]
    public function чужое_объявление_в_запросе_игнорируется(): void
    {
        $stranger = Company::factory()->create();
        $strangerListing = Listing::factory()->create(['company_id' => $stranger->id]);

        $this->unlock(['listing_id' => $strangerListing->id])->assertSessionHas('success');

        $this->assertNull(ContactUnlock::first()->listing_id);
    }

    #[Test]
    public function раскрытие_появляется_в_моих_контактах(): void
    {
        $this->unlock();

        $this->actingAs($this->user)
            ->get('/cabinet/contacts')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->has('contacts', 1)
                ->where('contacts.0.company.name', 'ООО «Поставщик»')
                ->where('contacts.0.phones.0', '+998 90 555-11-22'),
            );
    }
}
