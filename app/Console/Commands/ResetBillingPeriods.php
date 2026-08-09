<?php

declare(strict_types=1);

namespace App\Console\Commands;

use App\Models\Subscription;
use App\Models\Wallet;
use App\Services\OrderService;
use App\Support\Notifier;
use Illuminate\Console\Command;

/**
 * Начало нового расчётного периода: сброс месячных лимитов
 * и завершение подписок, у которых кончился оплаченный срок.
 *
 * Кредиты при сбросе не сгорают — по §3.2 ТЗ они живут 12 месяцев.
 * Обнуляется только счётчик израсходованных контактов и начисляются
 * единицы продвижения по тарифу.
 *
 * Здесь же выставляются счета на продление: подписка с автопродлением
 * получает счёт за неделю до конца срока.
 */
class ResetBillingPeriods extends Command
{
    protected $signature = 'billing:reset-periods';

    protected $description = 'Сбросить месячные лимиты и закрыть истёкшие подписки';

    /** За сколько дней до конца срока выставляется счёт на продление. */
    private const RENEW_BEFORE_DAYS = 7;

    public function handle(Notifier $notifier, OrderService $orders): int
    {
        $this->issueRenewals($orders);
        $this->expireSubscriptions($notifier);
        $this->resetWallets();

        return self::SUCCESS;
    }

    /**
     * Счёт на продление за неделю до конца срока.
     *
     * Автопродление здесь — не автосписание: денег с расчётного счёта
     * компании никто не снимает. Площадка заранее выставляет счёт, и у
     * бухгалтерии остаётся неделя, чтобы провести платёж без разрыва
     * в тарифе. Флаг auto_renew до этого не делал вообще ничего:
     * кабинет обещал продление, а продлевать было нечем.
     *
     * Когда подключится Payme или Click, здесь же появится списание
     * с привязанной карты — счёт останется для тех, кто платит переводом.
     */
    private function issueRenewals(OrderService $orders): void
    {
        $subscriptions = Subscription::query()
            ->with(['company.users', 'plan'])
            ->where('status', 'active')
            ->where('auto_renew', true)
            ->whereNotNull('ends_at')
            ->whereBetween('ends_at', [now(), now()->addDays(self::RENEW_BEFORE_DAYS)])
            ->get();

        $issued = 0;

        foreach ($subscriptions as $subscription) {
            $company = $subscription->company;
            $plan = $subscription->plan;
            $user = $company?->users->first();

            if ($company === null || $plan === null || $user === null) {
                continue;
            }

            // Счёт на продление уже выставлен — второй не нужен
            $pending = $company->payments()
                ->where('status', 'pending')
                ->where('plan_id', $plan->id)
                ->exists();

            if ($pending) {
                continue;
            }

            $orders->orderPlan($company, $plan, $user);
            $issued++;
        }

        $this->info("Выставлено счетов на продление: {$issued}.");
    }

    /**
     * Подписка с истёкшим сроком и без автопродления закрывается.
     *
     * Компания при этом не блокируется: она просто переходит на Free,
     * потому что Company::plan() отдаёт бесплатный тариф в отсутствие
     * активной подписки. Отключать доступ за неоплату — способ потерять
     * клиента, который просто забыл продлить.
     */
    private function expireSubscriptions(Notifier $notifier): void
    {
        $subscriptions = Subscription::query()
            ->with('company')
            ->where('status', 'active')
            ->whereNotNull('ends_at')
            ->where('ends_at', '<=', now())
            ->get();

        foreach ($subscriptions as $subscription) {
            $subscription->forceFill(['status' => 'expired'])->save();

            if ($subscription->company !== null) {
                $notifier->company(
                    $subscription->company,
                    'payment',
                    'Срок тарифа истёк — вы перешли на Free',
                    [
                        'tone' => 'warning',
                        'body' => 'Объявления и контакты сохранены. Лимиты теперь действуют по бесплатному тарифу.',
                        'url' => '/cabinet/billing',
                    ],
                );
            }
        }

        $this->info("Закрыто подписок: {$subscriptions->count()}.");
    }

    private function resetWallets(): void
    {
        $wallets = Wallet::query()
            ->with('company')
            ->whereNotNull('period_resets_at')
            ->where('period_resets_at', '<=', now())
            ->get();

        foreach ($wallets as $wallet) {
            $plan = $wallet->company?->plan();

            $wallet->forceFill([
                'contacts_used_this_period' => 0,
                // Единицы продвижения выдаются заново по тарифу,
                // а не накапливаются: это месячная квота, а не кредиты
                'promo_units' => $plan?->promo_units ?? 0,
                'period_resets_at' => now()->addDays($plan?->period_days ?? 30),
            ])->save();
        }

        $this->info("Сброшено кошельков: {$wallets->count()}.");
    }
}
