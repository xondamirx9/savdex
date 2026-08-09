<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\Company;
use App\Models\Listing;
use App\Models\Plan;
use App\Models\Subscription;
use App\Models\User;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Лимит активных объявлений по тарифу.
 *
 * В статус «активно» ведут четыре пути: мастер публикации, продление
 * одного объявления, массовое продление и повторная отправка после
 * отказа. Проверка стояла только в первом — остальные три обходили
 * лимит, и платный тариф терял смысл.
 *
 * Сценарий обхода, который здесь закрыт: опубликовать до лимита,
 * заархивировать всё, опубликовать ещё столько же, затем одним
 * массовым действием продлить обе пачки.
 */
class ListingLimitTest extends TestCase
{
    use RefreshDatabase;

    private Company $company;

    private User $user;

    protected function setUp(): void
    {
        parent::setUp();

        Plan::create([
            'code' => 'free',
            'name' => 'Free',
            'price_usd' => 0,
            'listings_limit' => 2,
            'listing_days' => 30,
            'contacts_limit' => 3,
            'promo_units' => 0,
        ]);

        $this->company = Company::factory()->create();
        $this->user = User::factory()->create(['company_id' => $this->company->id]);
    }

    private function listing(string $status): Listing
    {
        return Listing::factory()->create([
            'company_id' => $this->company->id,
            'status' => $status,
            'expires_at' => $status === Listing::STATUS_EXPIRED ? now()->subDay() : now()->addDays(30),
        ]);
    }

    #[Test]
    public function продление_сверх_лимита_отклоняется(): void
    {
        $this->listing(Listing::STATUS_ACTIVE);
        $this->listing(Listing::STATUS_ACTIVE);
        $expired = $this->listing(Listing::STATUS_EXPIRED);

        $this->actingAs($this->user)
            ->post("/cabinet/listings/{$expired->id}/renew")
            ->assertSessionHas('error');

        $this->assertSame(Listing::STATUS_EXPIRED, $expired->fresh()->status);
        $this->assertSame(2, $this->company->activeListings()->count());
    }

    #[Test]
    public function продление_в_пределах_лимита_проходит(): void
    {
        $this->listing(Listing::STATUS_ACTIVE);
        $expired = $this->listing(Listing::STATUS_EXPIRED);

        $this->actingAs($this->user)
            ->post("/cabinet/listings/{$expired->id}/renew")
            ->assertSessionHas('success');

        $this->assertSame(Listing::STATUS_ACTIVE, $expired->fresh()->status);
    }

    /**
     * Массовое продление считает лимит на всю пачку сразу.
     *
     * Проверка по одному пропустила бы всех: каждое объявление
     * видело бы остаток, актуальный на свой момент.
     */
    #[Test]
    public function массовое_продление_не_обходит_лимит(): void
    {
        $ids = collect(range(1, 4))
            ->map(fn (): int => $this->listing(Listing::STATUS_ARCHIVED)->id)
            ->all();

        $this->actingAs($this->user)
            ->post('/cabinet/listings/bulk', ['action' => 'renew', 'ids' => $ids])
            ->assertSessionHas('error');

        $this->assertSame(0, $this->company->activeListings()->count());
    }

    #[Test]
    public function массовое_продление_в_пределах_лимита_проходит(): void
    {
        $ids = collect(range(1, 2))
            ->map(fn (): int => $this->listing(Listing::STATUS_ARCHIVED)->id)
            ->all();

        $this->actingAs($this->user)
            ->post('/cabinet/listings/bulk', ['action' => 'renew', 'ids' => $ids])
            ->assertSessionHas('success');

        $this->assertSame(2, $this->company->activeListings()->count());
    }

    /** Срок жизни объявления — часть тарифа, а не общая константа. */
    #[Test]
    public function срок_продления_берётся_из_тарифа(): void
    {
        $business = Plan::create([
            'code' => 'business',
            'name' => 'Business',
            'price_usd' => 39,
            'listings_limit' => 50,
            'listing_days' => 90,
            'contacts_limit' => 50,
            'promo_units' => 50,
        ]);

        Subscription::create([
            'company_id' => $this->company->id,
            'plan_id' => $business->id,
            'status' => 'active',
            'started_at' => now(),
            'ends_at' => now()->addDays(30),
        ]);

        $expired = $this->listing(Listing::STATUS_EXPIRED);

        $this->actingAs($this->user)->post("/cabinet/listings/{$expired->id}/renew");

        $this->assertSame(90, (int) round(now()->diffInDays($expired->fresh()->expires_at)));
    }

    /**
     * Повторный заход в мастер не должен плодить пустые черновики:
     * это GET, его дёргает предзагрузка ссылок и обновление страницы.
     */
    #[Test]
    public function повторный_заход_в_мастер_переиспользует_черновик(): void
    {
        $this->actingAs($this->user)->get('/cabinet/listings/create');
        $this->actingAs($this->user)->get('/cabinet/listings/create');
        $this->actingAs($this->user)->get('/cabinet/listings/create');

        $this->assertSame(1, $this->company->listings()->where('status', Listing::STATUS_DRAFT)->count());
    }
}
