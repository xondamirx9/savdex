<?php

declare(strict_types=1);

namespace App\Services;

use App\Models\Company;
use App\Models\Plan;
use App\Models\Subscription;
use App\Models\User;
use App\Models\Wallet;
use App\Support\Notifier;
use Illuminate\Support\Facades\DB;

/**
 * Назначение тарифа компании.
 *
 * Один путь и для оплаты, и для ручной выдачи из админки: смена
 * тарифа — это не только строка в subscriptions, но и промо-единицы
 * в кошельке, и сброс счётчика раскрытых контактов. Раздели эти шаги
 * по двум местам — и половина где-нибудь отвалится.
 */
class SubscriptionService
{
    public function __construct(private Notifier $notifier) {}

    /**
     * Выдать компании тариф.
     *
     * Прежняя подписка закрывается, а не удаляется: история «кто на чём
     * сидел» — единственный способ потом объяснить, почему у компании
     * были такие лимиты в прошлом месяце.
     *
     * @param  int|null  $days  срок; null — период из тарифа
     */
    public function assign(
        Company $company,
        Plan $plan,
        ?int $days = null,
        string $source = Subscription::SOURCE_PAYMENT,
        ?User $grantedBy = null,
        ?string $reason = null,
    ): Subscription {
        return DB::transaction(function () use ($company, $plan, $days, $source, $grantedBy, $reason): Subscription {
            Subscription::query()
                ->where('company_id', $company->id)
                ->where('status', 'active')
                ->lockForUpdate()
                ->update(['status' => 'expired', 'cancelled_at' => now()]);

            $days ??= $plan->period_days;

            $subscription = Subscription::create([
                'company_id' => $company->id,
                'plan_id' => $plan->id,
                'status' => 'active',
                'started_at' => now(),
                // Бессрочная подписка возможна только вручную: тариф
                // с period_days = 0 в кассе означал бы вечный доступ
                // за одну оплату
                'ends_at' => $days > 0 ? now()->addDays($days) : null,
                // Автопродление у подарочной подписки было бы обещанием,
                // которого никто не давал: она кончится молча
                'auto_renew' => $source === Subscription::SOURCE_PAYMENT,
                'source' => $source,
                'granted_by' => $grantedBy?->id,
                'grant_reason' => $reason,
            ]);

            $wallet = Wallet::firstOrCreate(['company_id' => $company->id]);

            /*
             * Промо-единицы тарифа начисляются сверх остатка, а счётчик
             * контактов обнуляется: новый тариф — новый период. Иначе
             * компания, перешедшая на Pro в конце месяца, получила бы
             * лимит Pro уже израсходованным.
             */
            $wallet->forceFill([
                'promo_units' => $wallet->promo_units + $plan->promo_units,
                'contacts_used_this_period' => 0,
                'period_resets_at' => $subscription->ends_at ?? now()->addDays(30),
            ])->save();

            $this->notifier->company(
                $company,
                'billing',
                $source === Subscription::SOURCE_MANUAL
                    ? "Вам назначен тариф «{$plan->name}»"
                    : "Тариф «{$plan->name}» активирован",
                [
                    'body' => $subscription->ends_at !== null
                        ? 'Действует до '.$subscription->ends_at->translatedFormat('d.m.Y').'.'
                        : 'Действует бессрочно.',
                    'tone' => 'success',
                    'url' => '/cabinet/billing',
                ],
            );

            return $subscription;
        });
    }
}
