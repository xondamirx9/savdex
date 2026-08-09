<?php

declare(strict_types=1);

namespace Tests\Feature\Admin;

use App\Models\Company;
use App\Models\Plan;
use App\Models\Subscription;
use App\Models\User;
use App\Models\UserNotification;
use App\Models\Wallet;
use App\Services\SubscriptionService;
use Illuminate\Foundation\Testing\RefreshDatabase;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Ручная выдача тарифа из админки.
 *
 * Продавцы обещают доступ раньше, чем приходят деньги: «включите VIP,
 * счёт оплатим в пятницу». Без этой операции остаётся править базу
 * руками — и тогда никто не помнит, кому и почему дали бесплатно.
 */
class SubscriptionGrantTest extends TestCase
{
    use RefreshDatabase;

    private function plan(string $code, array $overrides = []): Plan
    {
        return Plan::create([
            'code' => $code,
            'name' => strtoupper($code),
            'price_usd' => 0,
            'period_days' => 30,
            'listing_days' => 30,
            'listings_limit' => 10,
            'contacts_limit' => 20,
            'promo_units' => 5,
            'verification_days' => 3,
            ...$overrides,
        ]);
    }

    #[Test]
    public function выдача_тарифа_создаёт_подписку_с_основанием(): void
    {
        $company = Company::factory()->create();
        $admin = User::factory()->create(['is_admin' => true, 'admin_role' => User::ADMIN_SUPERADMIN]);
        $plan = $this->plan('vip');

        $subscription = app(SubscriptionService::class)->assign(
            $company,
            $plan,
            days: 14,
            source: Subscription::SOURCE_MANUAL,
            grantedBy: $admin,
            reason: 'Дебиторка: счёт №142',
        );

        $this->assertTrue($subscription->isManual());
        $this->assertSame($admin->id, $subscription->granted_by);
        $this->assertSame('Дебиторка: счёт №142', $subscription->grant_reason);
        $this->assertSame(14, $subscription->daysLeft());

        // Подарочная подписка не продлевается сама: продление без
        // оплаты — обещание, которого площадка не давала
        $this->assertFalse($subscription->auto_renew);
    }

    /** Прежняя подписка закрывается, а не удаляется — история нужна. */
    #[Test]
    public function прежняя_подписка_закрывается_и_остаётся_в_истории(): void
    {
        $company = Company::factory()->create();
        $free = $this->plan(Plan::FREE);
        $pro = $this->plan('pro');

        $service = app(SubscriptionService::class);
        $old = $service->assign($company, $free);
        $service->assign($company, $pro);

        $this->assertSame('expired', $old->fresh()->status);
        $this->assertSame(2, Subscription::where('company_id', $company->id)->count());
        $this->assertSame($pro->id, $company->fresh()->plan()->id);
    }

    /**
     * Счётчик раскрытий обнуляется при смене тарифа: иначе компания,
     * перешедшая на Pro в конце месяца, получила бы новый лимит
     * уже израсходованным.
     */
    #[Test]
    public function смена_тарифа_обнуляет_счётчик_и_начисляет_промо(): void
    {
        $company = Company::factory()->create();
        Wallet::create([
            'company_id' => $company->id,
            'credits' => 7,
            'promo_units' => 2,
            'contacts_used_this_period' => 19,
        ]);

        app(SubscriptionService::class)->assign($company, $this->plan('pro', ['promo_units' => 5]));

        $wallet = $company->fresh()->wallet;

        $this->assertSame(0, $wallet->contacts_used_this_period);
        $this->assertSame(7, $wallet->promo_units, 'промо тарифа начисляются сверх остатка');
        $this->assertSame(7, $wallet->credits, 'купленные кредиты сменой тарифа не трогаются');
    }

    /** Ноль дней — бессрочный доступ: так выдают партнёрам. */
    #[Test]
    public function ноль_дней_означает_бессрочно(): void
    {
        $company = Company::factory()->create();

        $subscription = app(SubscriptionService::class)->assign(
            $company,
            $this->plan('partner'),
            days: 0,
            source: Subscription::SOURCE_MANUAL,
        );

        $this->assertNull($subscription->ends_at);
        $this->assertNull($subscription->daysLeft());
        $this->assertTrue($subscription->isActive());
    }

    #[Test]
    public function компания_узнаёт_о_выданном_тарифе(): void
    {
        $company = Company::factory()->create();
        $user = User::factory()->create(['company_id' => $company->id]);

        app(SubscriptionService::class)->assign(
            $company,
            $this->plan('vip'),
            source: Subscription::SOURCE_MANUAL,
            reason: 'VIP-партнёр',
        );

        $this->assertTrue(
            UserNotification::where('user_id', $user->id)->exists(),
            'выдача тарифа без уведомления остаётся незамеченной',
        );
    }
}
