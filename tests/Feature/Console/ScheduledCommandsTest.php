<?php

declare(strict_types=1);

namespace Tests\Feature\Console;

use App\Models\Company;
use App\Models\Listing;
use App\Models\Payment;
use App\Models\Plan;
use App\Models\Promotion;
use App\Models\PromotionType;
use App\Models\Review;
use App\Models\Subscription;
use App\Models\User;
use App\Models\Wallet;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Задачи по расписанию.
 *
 * Раньше их не существовало вовсе, и это ломало продукт молча:
 * объявления висели в выдаче после истечения срока, места «ТОП
 * категории» оставались занятыми навсегда после первых трёх покупок,
 * месячные лимиты не обнулялись, рейтинг у всех оставался нулевым.
 */
class ScheduledCommandsTest extends TestCase
{
    use RefreshDatabase;

    private function plan(): Plan
    {
        return Plan::firstOrCreate(['code' => 'free'], [
            'name' => 'Free',
            'price_usd' => 0,
            'listings_limit' => 4,
            'listing_days' => 30,
            'contacts_limit' => 3,
            'promo_units' => 5,
            'period_days' => 30,
        ]);
    }

    #[Test]
    public function истёкшее_объявление_снимается_с_публикации(): void
    {
        $this->plan();
        $company = Company::factory()->create();
        User::factory()->create(['company_id' => $company->id]);

        $expired = Listing::factory()->create([
            'company_id' => $company->id,
            'status' => Listing::STATUS_ACTIVE,
            'expires_at' => now()->subDay(),
        ]);

        $alive = Listing::factory()->create([
            'company_id' => $company->id,
            'status' => Listing::STATUS_ACTIVE,
            'expires_at' => now()->addDays(20),
        ]);

        $this->artisan('listings:expire')->assertSuccessful();

        $this->assertSame(Listing::STATUS_EXPIRED, $expired->fresh()->status);
        $this->assertSame(Listing::STATUS_ACTIVE, $alive->fresh()->status, 'Живое объявление трогать нельзя');
    }

    #[Test]
    public function о_снятии_приходит_уведомление(): void
    {
        $this->plan();
        $company = Company::factory()->create();
        $user = User::factory()->create(['company_id' => $company->id]);

        Listing::factory()->create([
            'company_id' => $company->id,
            'status' => Listing::STATUS_ACTIVE,
            'expires_at' => now()->subHour(),
        ]);

        $this->artisan('listings:expire');

        $this->assertSame(1, $user->alerts()->count());
    }

    /**
     * Слоты ограничены, и статус active держит место занятым.
     * Без завершения продвижений «ТОП главной» после шести покупок
     * не смог бы купить никто и никогда.
     */
    #[Test]
    public function истёкшее_продвижение_освобождает_место(): void
    {
        $company = Company::factory()->create();
        $listing = Listing::factory()->create([
            'company_id' => $company->id,
            'status' => Listing::STATUS_ACTIVE,
            'impressions_count' => 1430,
        ]);

        $type = PromotionType::create([
            'code' => 'category_top',
            'name' => 'ТОП категории',
            'description' => 'Первые позиции',
            'cost_units' => 5,
            'duration_days' => 7,
            'slots' => 1,
        ]);

        $promotion = Promotion::create([
            'listing_id' => $listing->id,
            'company_id' => $company->id,
            'promotion_type_id' => $type->id,
            'units_spent' => 5,
            'status' => 'active',
            'starts_at' => now()->subDays(8),
            'ends_at' => now()->subDay(),
            'impressions_before' => 412,
        ]);

        $this->assertFalse($type->hasFreeSlot(), 'До завершения место занято');

        $this->artisan('promotions:finish')->assertSuccessful();

        $promotion->refresh();

        $this->assertSame('finished', $promotion->status);
        $this->assertSame(1430, $promotion->impressions_after);
        $this->assertSame(247, $promotion->effect(), 'Эффект считается по факту завершения');
        $this->assertTrue($type->fresh()->hasFreeSlot(), 'Место должно освободиться');
    }

    #[Test]
    public function истёкшая_подписка_закрывается_а_компания_переходит_на_free(): void
    {
        $free = $this->plan();

        $business = Plan::create([
            'code' => 'business',
            'name' => 'Business',
            'price_usd' => 39,
            'listings_limit' => 50,
            'listing_days' => 90,
            'contacts_limit' => 50,
            'promo_units' => 50,
        ]);

        $company = Company::factory()->create();
        User::factory()->create(['company_id' => $company->id]);

        Subscription::create([
            'company_id' => $company->id,
            'plan_id' => $business->id,
            'status' => 'active',
            'started_at' => now()->subDays(31),
            'ends_at' => now()->subDay(),
            'auto_renew' => false,
        ]);

        $this->artisan('billing:reset-periods')->assertSuccessful();

        $this->assertSame('expired', Subscription::first()->status);
        // Компания не блокируется, а переходит на бесплатный тариф
        $this->assertSame($free->id, $company->fresh()->plan()->id);
    }

    #[Test]
    public function месячные_лимиты_обнуляются_а_кредиты_остаются(): void
    {
        $this->plan();
        $company = Company::factory()->create();

        $wallet = Wallet::create([
            'company_id' => $company->id,
            'credits' => 12,
            'promo_units' => 0,
            'contacts_used_this_period' => 3,
            'period_resets_at' => now()->subHour(),
        ]);

        $this->artisan('billing:reset-periods')->assertSuccessful();

        $wallet->refresh();

        $this->assertSame(0, $wallet->contacts_used_this_period);
        $this->assertSame(5, $wallet->promo_units, 'Единицы продвижения выдаются заново по тарифу');
        // Кредиты живут 12 месяцев и при смене периода не сгорают
        $this->assertSame(12, $wallet->credits);
        $this->assertTrue($wallet->period_resets_at->isFuture());
    }

    /**
     * Рейтинг байесовский: одна пятёрка не должна ставить новичка
     * выше компании с двадцатью отзывами и средним 4,8.
     *
     * Проверяется именно подтягивание к среднему по площадке. Чтобы
     * оно было заметно, среднее должно отличаться от пятёрки — иначе
     * формула честно даёт 5,0 обеим, и тест ничего не измеряет.
     */
    #[Test]
    public function рейтинг_учитывает_число_отзывов(): void
    {
        $newcomer = Company::factory()->create();
        $veteran = Company::factory()->create();

        // Фон площадки: средние оценки, из-за которых новичок
        // с единственной пятёркой подтянется вниз
        $background = Company::factory()->create();

        foreach (range(1, 10) as $i) {
            Review::create([
                'company_id' => $background->id,
                'author_company_id' => Company::factory()->create()->id,
                'rating' => 3,
                'body' => "Средне, без восторга, отгрузка {$i}",
                'status' => 'published',
            ]);
        }

        Review::create([
            'company_id' => $newcomer->id,
            'author_company_id' => Company::factory()->create()->id,
            'rating' => 5,
            'body' => 'Отличный поставщик, всё точно в срок',
            'status' => 'published',
        ]);

        foreach (range(1, 20) as $i) {
            Review::create([
                'company_id' => $veteran->id,
                'author_company_id' => Company::factory()->create()->id,
                'rating' => 5,
                'body' => "Работаем не первый год, отгрузка {$i}",
                'status' => 'published',
            ]);
        }

        $this->artisan('ratings:recalculate')->assertSuccessful();

        $newcomerRating = (float) $newcomer->fresh()->rating;
        $veteranRating = (float) $veteran->fresh()->rating;

        $this->assertGreaterThan(
            $newcomerRating,
            $veteranRating,
            'Двадцать пятёрок должны весить больше одной',
        );

        // Новичок подтянут к среднему, а не получил чистые 5,0
        $this->assertLessThan(5.0, $newcomerRating);

        $this->assertSame(1, $newcomer->fresh()->reviews_count);
        $this->assertSame(20, $veteran->fresh()->reviews_count);
    }

    #[Test]
    public function компания_без_отзывов_получает_нулевой_рейтинг(): void
    {
        $company = Company::factory()->create(['rating' => 4.8, 'reviews_count' => 34]);

        $this->artisan('ratings:recalculate');

        // Выдуманный рейтинг из демо-данных должен обнулиться:
        // показывать 4.8 при нуле отзывов — обман покупателя
        $this->assertSame(0.0, (float) $company->fresh()->rating);
        $this->assertSame(0, $company->fresh()->reviews_count);
    }

    // ── Счета на продление ───────────────────────────────────

    /** @param array<string, mixed> $overrides */
    private function subscriptionEndingIn(int $days, array $overrides = []): Subscription
    {
        $company = Company::factory()->create();
        User::factory()->for($company)->create();

        $plan = Plan::create([
            'code' => 'pro-'.uniqid(), 'name' => 'Pro', 'price_usd' => 39, 'period_days' => 30,
            'listing_days' => 30, 'listings_limit' => 50, 'contacts_limit' => 50,
            'promo_units' => 10, 'verification_days' => 3,
        ]);

        return Subscription::create([
            'company_id' => $company->id,
            'plan_id' => $plan->id,
            'status' => 'active',
            'started_at' => now()->subDays(30 - $days),
            'ends_at' => now()->addDays($days),
            'auto_renew' => true,
            'source' => Subscription::SOURCE_PAYMENT,
            ...$overrides,
        ]);
    }

    /**
     * Автопродление — это счёт заранее, а не автосписание.
     *
     * Флаг auto_renew до этого не делал ничего: кабинет обещал продление,
     * а продлевать было нечем, и подписка молча истекала.
     */
    #[Test]
    public function подписка_на_исходе_получает_счёт_на_продление(): void
    {
        $subscription = $this->subscriptionEndingIn(3);

        $this->artisan('billing:reset-periods')->assertSuccessful();

        $payment = Payment::where('company_id', $subscription->company_id)->first();

        $this->assertNotNull($payment, 'счёт на продление должен быть выставлен');
        $this->assertSame('pending', $payment->status);
        $this->assertSame($subscription->plan_id, $payment->plan_id);
    }

    /** До срока ещё далеко — счёт рано. */
    #[Test]
    public function подписка_с_запасом_счёт_не_получает(): void
    {
        $this->subscriptionEndingIn(20);

        $this->artisan('billing:reset-periods');

        $this->assertSame(0, Payment::count());
    }

    #[Test]
    public function без_автопродления_счёт_не_выставляется(): void
    {
        $this->subscriptionEndingIn(3, ['auto_renew' => false]);

        $this->artisan('billing:reset-periods');

        $this->assertSame(0, Payment::count());
    }

    /** Второй счёт на тот же тариф не нужен: платят по одному. */
    #[Test]
    public function счёт_на_продление_не_дублируется(): void
    {
        $this->subscriptionEndingIn(3);

        $this->artisan('billing:reset-periods');
        $this->artisan('billing:reset-periods');

        $this->assertSame(1, Payment::count());
    }
}
