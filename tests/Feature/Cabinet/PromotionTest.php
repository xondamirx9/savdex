<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\Company;
use App\Models\Listing;
use App\Models\Promotion;
use App\Models\PromotionType;
use App\Models\User;
use App\Models\Wallet;
use App\Models\WalletTransaction;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Продвижение объявлений: списание единиц и ограничение мест.
 *
 * Здесь тратятся деньги компании, поэтому проверяется не только
 * успешный путь, но и все отказы: без них ошибка стоит выручки
 * или возврата.
 */
class PromotionTest extends TestCase
{
    use RefreshDatabase;

    private Company $company;

    private User $user;

    private Listing $listing;

    protected function setUp(): void
    {
        parent::setUp();

        $this->company = Company::factory()->create();
        $this->user = User::factory()->create(['company_id' => $this->company->id]);

        $this->listing = Listing::factory()->create([
            'company_id' => $this->company->id,
            'status' => Listing::STATUS_ACTIVE,
            'impressions_count' => 412,
        ]);

        Wallet::create(['company_id' => $this->company->id, 'promo_units' => 10, 'credits' => 0]);
    }

    private function type(array $overrides = []): PromotionType
    {
        return PromotionType::create([
            'code' => 'category_top',
            'name' => 'ТОП категории',
            'description' => 'Первые три позиции в категории.',
            'cost_units' => 5,
            'duration_days' => 7,
            'slots' => 3,
            ...$overrides,
        ]);
    }

    #[Test]
    public function запуск_списывает_единицы_и_фиксирует_базу_показов(): void
    {
        $type = $this->type();

        $this->actingAs($this->user)
            ->post('/cabinet/promo', [
                'listing_id' => $this->listing->id,
                'promotion_type_id' => $type->id,
            ])
            ->assertSessionHas('success');

        $promotion = Promotion::first();

        $this->assertNotNull($promotion);
        $this->assertSame('active', $promotion->status);
        $this->assertSame(5, $promotion->units_spent);

        // База показов фиксируется на старте: посчитать эффект
        // задним числом нельзя — периоды накладываются
        $this->assertSame(412, $promotion->impressions_before);

        $this->assertSame(5, $this->company->wallet->fresh()->promo_units);
    }

    /** Остаток обязан быть выводим из истории — иначе спор не закрыть. */
    #[Test]
    public function списание_попадает_в_историю_кошелька(): void
    {
        $this->actingAs($this->user)->post('/cabinet/promo', [
            'listing_id' => $this->listing->id,
            'promotion_type_id' => $this->type()->id,
        ]);

        $transaction = WalletTransaction::first();

        $this->assertNotNull($transaction);
        $this->assertSame(-5, $transaction->amount);
        $this->assertSame(5, $transaction->balance_after);
        $this->assertSame('promotion', $transaction->reason);
    }

    #[Test]
    public function не_хватает_единиц_отказ_без_списания(): void
    {
        $type = $this->type(['cost_units' => 50]);

        $this->actingAs($this->user)
            ->post('/cabinet/promo', [
                'listing_id' => $this->listing->id,
                'promotion_type_id' => $type->id,
            ])
            ->assertSessionHas('error');

        $this->assertSame(0, Promotion::count());
        $this->assertSame(10, $this->company->wallet->fresh()->promo_units);
    }

    /**
     * Одно и то же продвижение дважды на одном объявлении — деньги
     * на ветер: второе не усиливает первое.
     */
    #[Test]
    public function повторный_запуск_того_же_инструмента_отклоняется(): void
    {
        $type = $this->type(['cost_units' => 1]);

        $payload = ['listing_id' => $this->listing->id, 'promotion_type_id' => $type->id];

        $this->actingAs($this->user)->post('/cabinet/promo', $payload);
        $this->actingAs($this->user)->post('/cabinet/promo', $payload)->assertSessionHas('error');

        $this->assertSame(1, Promotion::count());
        $this->assertSame(9, $this->company->wallet->fresh()->promo_units);
    }

    /**
     * Места ограничены: без этого инструмент продаётся бесконечно
     * и перестаёт работать сразу у всех.
     */
    #[Test]
    public function места_ограничены(): void
    {
        $type = $this->type(['cost_units' => 1, 'slots' => 1]);

        /*
         * Место занято другой компанией в той же категории. Категория
         * обязательна: места считаются внутри неё, и продвижение без
         * category_id не занимает ничьё место.
         */
        $other = Company::factory()->create();
        $otherListing = Listing::factory()->create([
            'company_id' => $other->id,
            'status' => Listing::STATUS_ACTIVE,
            'category_id' => $this->listing->category_id,
        ]);

        Promotion::create([
            'listing_id' => $otherListing->id,
            'company_id' => $other->id,
            'promotion_type_id' => $type->id,
            'category_id' => $otherListing->category_id,
            'units_spent' => 1,
            'status' => 'active',
            'starts_at' => now(),
            'ends_at' => now()->addDays(7),
            'impressions_before' => 0,
        ]);

        $this->actingAs($this->user)
            ->post('/cabinet/promo', [
                'listing_id' => $this->listing->id,
                'promotion_type_id' => $type->id,
            ])
            ->assertSessionHas('error');

        $this->assertSame(10, $this->company->wallet->fresh()->promo_units);
    }

    #[Test]
    public function чужое_объявление_продвигать_нельзя(): void
    {
        $stranger = Company::factory()->create();
        $strangerListing = Listing::factory()->create([
            'company_id' => $stranger->id,
            'status' => Listing::STATUS_ACTIVE,
        ]);

        $this->actingAs($this->user)
            ->post('/cabinet/promo', [
                'listing_id' => $strangerListing->id,
                'promotion_type_id' => $this->type()->id,
            ])
            ->assertSessionHas('error');

        $this->assertSame(0, Promotion::count());
    }

    #[Test]
    public function черновик_продвигать_нельзя(): void
    {
        $draft = Listing::factory()->create([
            'company_id' => $this->company->id,
            'status' => Listing::STATUS_DRAFT,
        ]);

        $this->actingAs($this->user)
            ->post('/cabinet/promo', [
                'listing_id' => $draft->id,
                'promotion_type_id' => $this->type()->id,
            ])
            ->assertSessionHas('error');

        $this->assertSame(0, Promotion::count());
    }

    #[Test]
    public function запуск_создаёт_уведомление_и_событие(): void
    {
        $this->actingAs($this->user)->post('/cabinet/promo', [
            'listing_id' => $this->listing->id,
            'promotion_type_id' => $this->type()->id,
        ]);

        $this->assertSame(1, $this->company->events()->count());
        $this->assertSame(1, $this->user->alerts()->count());
    }
}
