<?php

declare(strict_types=1);

namespace App\Services;

use App\Exceptions\PromoCodeRejected;
use App\Models\Company;
use App\Models\Payment;
use App\Models\PromoCode;
use App\Models\Subscription;
use App\Models\User;
use Illuminate\Support\Facades\DB;

/**
 * Погашение промокода: бесплатный период тарифа без счёта и оплаты.
 *
 * Акция для тех, кто ещё не платил: она нужна, чтобы человек попробовал
 * платный тариф и остался, а не чтобы действующий клиент заменил
 * оплаченную подписку подарком.
 *
 * Тариф выдаётся тем же SubscriptionService, что и оплата, — иначе
 * подарочная подписка прошла бы мимо кошелька и счётчика раскрытий.
 * auto_renew при этом остаётся выключенным: источник не SOURCE_PAYMENT,
 * счёт на продление не выставляется, и по окончании месяца компания
 * сама возвращается на бесплатный тариф.
 */
class PromoCodeService
{
    public function __construct(private SubscriptionService $subscriptions) {}

    /**
     * Активировать код для компании.
     *
     * @throws PromoCodeRejected причина отказа — в сообщении, её видит человек
     */
    public function redeem(string $input, Company $company, User $user): Subscription
    {
        $code = PromoCode::normalize($input);

        if ($code === '') {
            throw new PromoCodeRejected('Введите промокод');
        }

        return DB::transaction(function () use ($code, $company, $user): Subscription {
            $promo = PromoCode::query()->where('code', $code)->first();

            if ($promo === null) {
                throw new PromoCodeRejected('Такого промокода нет. Проверьте, правильно ли он набран.');
            }

            $this->assertCodeUsable($promo);
            $this->assertCompanyEligible($company);

            $plan = $promo->plan;

            if ($plan === null || ! $plan->is_active) {
                throw new PromoCodeRejected('Тариф по этому промокоду больше не выдаётся. Напишите в поддержку.');
            }

            if ($promo->days < 1) {
                throw new PromoCodeRejected('Промокод выпущен с ошибкой: срок доступа не задан. Напишите в поддержку.');
            }

            /*
             * Захват кода — одним условным UPDATE, а не проверкой
             * с последующей записью: lockForUpdate на SQLite (а именно
             * он стоит на хостинге) ничего не блокирует, и два
             * одновременных нажатия проходили обе проверки used_at.
             * Здесь же выигрывает ровно один запрос: второму база
             * вернёт ноль изменённых строк.
             *
             * Уникальный индекс на used_by_company_id страхует от того
             * же с разными кодами: одна компания — один погашенный код.
             */
            $captured = PromoCode::query()
                ->where('id', $promo->id)
                ->whereNull('used_at')
                ->update([
                    'used_at' => now(),
                    'used_by_company_id' => $company->id,
                    'used_by_user_id' => $user->id,
                    'updated_at' => now(),
                ]);

            if ($captured !== 1) {
                throw new PromoCodeRejected('Этот промокод уже активирован.');
            }

            $subscription = $this->subscriptions->assign(
                company: $company,
                plan: $plan,
                days: $promo->days,
                source: Subscription::SOURCE_PROMO,
                grantedBy: $user,
                reason: "Промокод {$promo->code}",
            );

            // Связь с подпиской дописывается после выдачи: упади она —
            // откатится вся транзакция вместе с захватом кода
            PromoCode::query()->where('id', $promo->id)->update(['subscription_id' => $subscription->id]);

            return $subscription;
        });
    }

    /**
     * Подходит ли компания под акцию — для показа формы в кабинете.
     *
     * Те же правила, что и при активации, а не их копия: разъехавшись,
     * они дали бы форму, которая на любой код отвечает отказом.
     */
    public function eligible(Company $company): bool
    {
        try {
            $this->assertCompanyEligible($company);

            return true;
        } catch (PromoCodeRejected) {
            return false;
        }
    }

    /** @throws PromoCodeRejected */
    private function assertCodeUsable(PromoCode $promo): void
    {
        if ($promo->isUsed()) {
            throw new PromoCodeRejected('Этот промокод уже активирован.');
        }

        if ($promo->isExpired()) {
            throw new PromoCodeRejected('Срок действия промокода истёк.');
        }

        if (! $promo->is_active) {
            throw new PromoCodeRejected('Промокод отключён. Напишите в поддержку, если получили его недавно.');
        }
    }

    /**
     * Условия акции для компании.
     *
     * @throws PromoCodeRejected
     */
    private function assertCompanyEligible(Company $company): void
    {
        $alreadyRedeemed = PromoCode::query()
            ->where('used_by_company_id', $company->id)
            ->exists();

        if ($alreadyRedeemed) {
            throw new PromoCodeRejected('Ваша компания уже активировала промокод — второй раз акция не действует.');
        }

        /*
         * Платившая компания под акцию не подходит: промокод — это
         * знакомство с платным тарифом, а не способ не платить дальше.
         * Смотрим на оплаченные счета, а не на текущую подписку:
         * оплата в прошлом году — тоже оплата.
         */
        // Возвращённый платёж — тоже оплата в прошлом: вернуть деньги
        // и следом получить месяц бесплатно акция не предполагает
        $hasPaid = Payment::query()
            ->where('company_id', $company->id)
            ->whereIn('status', ['paid', 'refunded'])
            ->exists();

        if ($hasPaid) {
            throw new PromoCodeRejected('Промокод действует только для компаний, которые ещё не оплачивали тариф.');
        }

        /*
         * Активный платный тариф закрывать подарочным нельзя: assign()
         * закрывает прежнюю подписку молча, и компания, которой тариф
         * выдал администратор, потеряла бы остаток срока.
         */
        $active = $company->subscription;

        if ($active !== null && $active->isActive()) {
            throw new PromoCodeRejected('У вашей компании уже есть действующий тариф. Промокод можно активировать, когда он закончится.');
        }
    }
}
