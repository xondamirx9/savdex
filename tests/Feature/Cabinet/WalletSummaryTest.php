<?php

declare(strict_types=1);

namespace Tests\Feature\Cabinet;

use App\Models\Company;
use App\Models\Plan;
use App\Models\Subscription;
use App\Models\User;
use App\Models\Wallet;
use Illuminate\Foundation\Testing\RefreshDatabase;
use Inertia\Testing\AssertableInertia;
use PHPUnit\Framework\Attributes\Test;
use Tests\TestCase;

/**
 * Счётчик контактов в шапке.
 *
 * Шапка читала auth.credits — проп, который никто не клал в общие
 * данные. Всем и всегда показывался ноль: компания на платном тарифе
 * с полусотней контактов в месяц видела «0 кредитов» и делала вывод,
 * что открыть ничего не может.
 *
 * Считается сумма: расходуется сначала месячный лимит тарифа, потом
 * купленные кредиты, поэтому человека интересует «сколько я могу
 * открыть», а не остаток одного из двух счётчиков.
 */
class WalletSummaryTest extends TestCase
{
    use RefreshDatabase;

    /** @param array<string, mixed> $planOverrides */
    private function userOn(array $planOverrides, int $credits = 0, int $used = 0): User
    {
        $company = Company::factory()->create();

        $plan = Plan::create([
            'code' => 'test-'.uniqid(), 'name' => 'Test', 'price_usd' => 0, 'period_days' => 30,
            'listing_days' => 30, 'listings_limit' => 10, 'contacts_limit' => 10,
            'promo_units' => 0, 'verification_days' => 3,
            ...$planOverrides,
        ]);

        Subscription::create([
            'company_id' => $company->id,
            'plan_id' => $plan->id,
            'status' => 'active',
            'started_at' => now(),
            'ends_at' => now()->addDays(30),
        ]);

        Wallet::create([
            'company_id' => $company->id,
            'credits' => $credits,
            'contacts_used_this_period' => $used,
            'period_resets_at' => now()->addDays(30),
        ]);

        return User::factory()->for($company)->create(['email_verified_at' => now()]);
    }

    #[Test]
    public function счётчик_складывает_лимит_тарифа_и_кредиты(): void
    {
        $user = $this->userOn(['contacts_limit' => 50], credits: 30, used: 8);

        $this->actingAs($user)
            ->get('/cabinet')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('contactsLeft.plan_left', 42)
                ->where('contactsLeft.credits', 30)
                ->where('contactsLeft.total', 72),
            );
    }

    /**
     * Главный случай: тариф есть, кредитов не покупали. Именно здесь
     * человек видел ноль и шёл покупать то, что у него уже оплачено.
     */
    #[Test]
    public function без_купленных_кредитов_счётчик_показывает_лимит_тарифа(): void
    {
        $user = $this->userOn(['contacts_limit' => 50], credits: 0);

        $this->actingAs($user)
            ->get('/cabinet')
            ->assertInertia(fn (AssertableInertia $page) => $page->where('contactsLeft.total', 50));
    }

    /** null у безлимитного тарифа — это «без ограничений», а не ноль. */
    #[Test]
    public function безлимитный_тариф_отдаёт_null(): void
    {
        $user = $this->userOn(['contacts_limit' => null], credits: 5);

        $this->actingAs($user)
            ->get('/cabinet')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('contactsLeft.plan_left', null)
                ->where('contactsLeft.total', null),
            );
    }

    /** Израсходованный лимит не уходит в минус. */
    #[Test]
    public function перерасход_лимита_не_даёт_отрицательного_остатка(): void
    {
        $user = $this->userOn(['contacts_limit' => 3], credits: 2, used: 5);

        $this->actingAs($user)
            ->get('/cabinet')
            ->assertInertia(fn (AssertableInertia $page) => $page
                ->where('contactsLeft.plan_left', 0)
                ->where('contactsLeft.total', 2),
            );
    }

    /** У гостя счётчика нет — показывать в шапке нечего. */
    #[Test]
    public function гостю_счётчик_не_отдаётся(): void
    {
        $this->get('/')
            ->assertInertia(fn (AssertableInertia $page) => $page->where('contactsLeft', null));
    }

    #[Test]
    public function без_компании_счётчик_не_отдаётся(): void
    {
        $this->actingAs(User::factory()->create(['company_id' => null]))
            ->get('/')
            ->assertInertia(fn (AssertableInertia $page) => $page->where('contactsLeft', null));
    }
}
