<?php

declare(strict_types=1);

namespace App\Services;

use App\Models\Company;
use App\Models\CreditPack;
use App\Models\Payment;
use App\Models\Plan;
use App\Models\Subscription;
use App\Models\User;
use App\Models\Wallet;
use App\Support\CurrencyRate;
use App\Support\Notifier;
use Illuminate\Support\Facades\DB;

/**
 * Заказ и оплата: тарифы и пакеты кредитов.
 *
 * Оплата по счёту, а не картой. Так покупает бизнес в Узбекистане:
 * компания получает счёт, платит переводом со своего расчётного счёта
 * и ждёт зачисления. Карточная касса здесь была бы вторым способом,
 * а не первым — и её место в схеме оставлено: provider и external_id
 * ждут подключения Payme или Click.
 *
 * Пока деньги не пришли, купленное не выдаётся. Счёт со статусом
 * «ожидает оплаты» ничего не открывает — иначе тариф забирали бы,
 * не заплатив.
 */
class OrderService
{
    /** Сколько счёт ждёт оплаты, прежде чем его закроют как несостоявшийся. */
    public const EXPIRES_DAYS = 14;

    public function __construct(
        private readonly Notifier $notifier,
        private readonly SubscriptionService $subscriptions,
        private readonly CurrencyRate $rate,
    ) {}

    /** Счёт на тариф. */
    public function orderPlan(Company $company, Plan $plan, User $user): Payment
    {
        return $this->create($company, $user, [
            'purpose' => 'subscription',
            'plan_id' => $plan->id,
            'description' => "Тариф «{$plan->name}» на {$plan->period_days} дн.",
            'amount' => $plan->priceUzs($this->rate->usd()),
        ]);
    }

    /** Счёт на пакет кредитов. */
    public function orderCredits(Company $company, CreditPack $pack, User $user): Payment
    {
        return $this->create($company, $user, [
            'purpose' => 'credits',
            'credit_pack_id' => $pack->id,
            'description' => "Пакет «{$pack->name}»: {$pack->credits} раскрытий контактов",
            'amount' => $pack->priceUzs($this->rate->usd()),
        ]);
    }

    /**
     * @param  array<string, mixed>  $attributes
     */
    private function create(Company $company, User $user, array $attributes): Payment
    {
        $payment = Payment::create([
            'company_id' => $company->id,
            'currency' => 'UZS',
            'provider' => 'invoice',
            'status' => 'pending',
            ...$attributes,
        ]);

        $payment->forceFill(['number' => self::makeNumber($payment->id)])->save();

        $this->notifier->user(
            $user,
            'billing',
            "Счёт {$payment->number} сформирован",
            [
                'body' => $payment->description.'. Оплатите в течение '.self::EXPIRES_DAYS.' дней — доступ откроется после зачисления.',
                'url' => '/cabinet/billing',
            ],
        );

        return $payment;
    }

    /**
     * Номер счёта: SVD-000123.
     *
     * Из id, но с префиксом и дополнением нулями — так он выглядит как
     * номер документа, который называют бухгалтерии, а не как счётчик
     * заказов на площадке.
     */
    public static function makeNumber(int $id): string
    {
        return 'SVD-'.str_pad((string) $id, 6, '0', STR_PAD_LEFT);
    }

    /**
     * Деньги пришли — выдаём оплаченное.
     *
     * Единственное место, где счёт превращается в доступ. Начисление
     * и отметка об оплате идут одной транзакцией: оплаченный счёт без
     * начисленных кредитов — это претензия, а начисленные кредиты без
     * отметки об оплате — двойная выдача при повторном подтверждении.
     *
     * @return array{ok: bool, message: string}
     */
    public function confirm(Payment $payment, User $admin, ?string $note = null): array
    {
        if ($payment->status === 'paid') {
            return ['ok' => false, 'message' => 'Счёт уже оплачен — повторное начисление не выполнено.'];
        }

        $company = $payment->company;

        if ($company === null) {
            return ['ok' => false, 'message' => 'Компания удалена, начислять некому.'];
        }

        DB::transaction(function () use ($payment, $company, $admin, $note): void {
            $payment->forceFill([
                'status' => 'paid',
                'paid_at' => now(),
                'confirmed_by' => $admin->id,
                'admin_note' => $note,
            ])->save();

            match ($payment->purpose) {
                'subscription' => $this->grantPlan($payment, $company, $admin),
                'credits' => $this->grantCredits($payment, $company, $admin),
                default => null,
            };
        });

        $this->notifier->company(
            $company,
            'billing',
            "Оплата счёта {$payment->number} зачислена",
            ['tone' => 'success', 'body' => $payment->description, 'url' => '/cabinet/billing'],
        );

        return ['ok' => true, 'message' => 'Оплата зачислена, купленное начислено.'];
    }

    private function grantPlan(Payment $payment, Company $company, User $admin): void
    {
        $plan = $payment->plan;

        if ($plan === null) {
            return;
        }

        $subscription = $this->subscriptions->assign(
            $company,
            $plan,
            source: Subscription::SOURCE_PAYMENT,
            grantedBy: $admin,
            reason: "Оплата счёта {$payment->number}",
        );

        $payment->forceFill(['subscription_id' => $subscription->id])->save();
    }

    private function grantCredits(Payment $payment, Company $company, User $admin): void
    {
        $pack = $payment->creditPack;

        if ($pack === null) {
            return;
        }

        $wallet = Wallet::firstOrCreate(['company_id' => $company->id]);

        $wallet->grant('credits', $pack->credits, 'purchase', $payment, $admin->id);
    }

    /**
     * Счёт отменён: покупатель передумал или деньги не пришли.
     *
     * Строка остаётся — исчезнувший счёт выглядит как потерянный платёж,
     * а вопрос «а куда делся мой счёт на два миллиона» дороже строки
     * в таблице.
     */
    public function cancel(Payment $payment, ?User $admin = null, ?string $note = null): void
    {
        if ($payment->status === 'paid') {
            return;
        }

        $payment->forceFill([
            'status' => 'failed',
            'confirmed_by' => $admin?->id,
            'admin_note' => $note,
        ])->save();
    }
}
