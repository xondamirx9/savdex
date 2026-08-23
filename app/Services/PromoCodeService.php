<?php

declare(strict_types=1);

namespace App\Services;

use App\Exceptions\PromoCodeRejected;
use App\Models\Company;
use App\Models\Payment;
use App\Models\PromoCode;
use App\Models\Subscription;
use App\Models\User;
use Illuminate\Database\UniqueConstraintViolationException;
use Illuminate\Support\Facades\DB;

/**
 * Погашение промокода. Кодов два вида, и ведут они себя по-разному:
 *
 * — Код на бесплатный период выдаёт тариф сразу, без счёта и оплаты.
 *   Это акция для тех, кто ещё не платил: она нужна, чтобы человек
 *   попробовал платный тариф и остался, а не чтобы действующий клиент
 *   заменил оплаченную подписку подарком.
 *
 * — Скидочный код (discount_percent) ничего не дарит: он выставляет
 *   счёт на остаток цены тарифа, и покупатель уезжает на онлайн-оплату.
 *   Тариф включится, когда деньги дойдут, — тем же путём, что и любой
 *   оплаченный счёт. Ограничения «кто ещё не платил» здесь нет:
 *   скидка — повод заплатить, а не способ не платить.
 *
 * Тариф в обоих случаях выдаётся тем же SubscriptionService, что
 * и оплата, — иначе подписка прошла бы мимо кошелька и счётчика
 * раскрытий. У подарочной подписки auto_renew остаётся выключенным:
 * источник не SOURCE_PAYMENT, и по окончании срока компания сама
 * возвращается на бесплатный тариф.
 */
class PromoCodeService
{
    public function __construct(
        private SubscriptionService $subscriptions,
        private OrderService $orders,
    ) {}

    /**
     * Активировать код для компании.
     *
     * Возвращает подписку (код на бесплатный период) либо счёт со
     * скидкой (скидочный код) — по счёту вызывающая сторона уводит
     * покупателя на оплату.
     *
     * @throws PromoCodeRejected причина отказа — в сообщении, её видит человек
     */
    public function redeem(string $input, Company $company, User $user): Subscription|Payment
    {
        $code = PromoCode::normalize($input);

        if ($code === '') {
            throw new PromoCodeRejected('Введите промокод');
        }

        return DB::transaction(function () use ($code, $company, $user): Subscription|Payment {
            $promo = PromoCode::query()->where('code', $code)->first();

            if ($promo === null) {
                throw new PromoCodeRejected('Такого промокода нет. Проверьте, правильно ли он набран.');
            }

            /*
             * Повторный ввод своего же скидочного кода — не ошибка,
             * а «верните меня к оплате»: покупатель ушёл с платёжной
             * страницы и набрал код ещё раз. Отдаём тот же счёт,
             * а не отказ «уже активирован».
             */
            if ($promo->isDiscount() && $promo->used_by_company_id === $company->id) {
                return $this->resumeDiscount($promo, $company, $user);
            }

            $this->assertCodeUsable($promo);
            $this->assertNoRedeemedCode($company);

            $plan = $promo->plan;

            if ($plan === null || ! $plan->is_active) {
                throw new PromoCodeRejected('Тариф по этому промокоду больше не выдаётся. Напишите в поддержку.');
            }

            return $promo->isDiscount()
                ? $this->redeemDiscount($promo, $company, $user)
                : $this->redeemFree($promo, $company, $user);
        });
    }

    /**
     * Код на бесплатный период: тариф выдаётся сразу.
     */
    private function redeemFree(PromoCode $promo, Company $company, User $user): Subscription
    {
        $this->assertCompanyEligibleForFree($company);

        if ($promo->days < 1) {
            throw new PromoCodeRejected('Промокод выпущен с ошибкой: срок доступа не задан. Напишите в поддержку.');
        }

        $this->capture($promo, $company, $user);

        $subscription = $this->subscriptions->assign(
            company: $company,
            plan: $promo->plan,
            days: $promo->days,
            source: Subscription::SOURCE_PROMO,
            grantedBy: $user,
            reason: "Промокод {$promo->code}",
        );

        // Связь с подпиской дописывается после выдачи: упади она —
        // откатится вся транзакция вместе с захватом кода
        PromoCode::query()->where('id', $promo->id)->update(['subscription_id' => $subscription->id]);

        return $subscription;
    }

    /**
     * Скидочный код: счёт на остаток цены, тариф — после оплаты.
     *
     * Код захватывается сразу, при выставлении счёта, а не при оплате:
     * иначе два покупателя одновременно получили бы по счёту со скидкой
     * с одного кода, и второй заплатил бы за уже погашенный. Брошенный
     * счёт код не сжигает: отмена счёта возвращает код в оборот
     * (OrderService::cancel).
     */
    private function redeemDiscount(PromoCode $promo, Company $company, User $user): Payment
    {
        $percent = (int) $promo->discount_percent;

        if ($percent < 1 || $percent > 99) {
            throw new PromoCodeRejected('Промокод выпущен с ошибкой: размер скидки не задан. Напишите в поддержку.');
        }

        $this->capture($promo, $company, $user);

        return $this->orders->orderPlanWithPromo($company, $promo->plan, $user, $promo);
    }

    /**
     * Вернуть покупателя к счёту, выставленному по его же коду.
     *
     * Если открытого счёта нет, а скидка ещё не выкуплена (подписка
     * к коду не привязана), счёт выставляется заново: так бывает, когда
     * счёт отменили посреди карточной оплаты и код остался захваченным.
     * Код принадлежит этой компании — дать ей продолжить честнее,
     * чем отвечать «уже активирован» на её собственный код.
     */
    private function resumeDiscount(PromoCode $promo, Company $company, User $user): Payment
    {
        $pending = Payment::query()
            ->where('promo_code_id', $promo->id)
            ->where('company_id', $company->id)
            ->where('status', 'pending')
            ->latest()
            ->first();

        if ($pending !== null) {
            return $pending;
        }

        if ($promo->subscription_id !== null) {
            throw new PromoCodeRejected('Этот промокод уже активирован.');
        }

        $plan = $promo->plan;

        if ($plan === null || ! $plan->is_active) {
            throw new PromoCodeRejected('Тариф по этому промокоду больше не выдаётся. Напишите в поддержку.');
        }

        return $this->orders->orderPlanWithPromo($company, $plan, $user, $promo);
    }

    /**
     * Захват кода — одним условным UPDATE, а не проверкой с последующей
     * записью: lockForUpdate на SQLite (а именно он стоит на хостинге)
     * ничего не блокирует, и два одновременных нажатия проходили обе
     * проверки used_at. Здесь же выигрывает ровно один запрос: второму
     * база вернёт ноль изменённых строк.
     *
     * Уникальный индекс на used_by_company_id страхует от того же
     * с разными кодами: одна компания — один погашенный код.
     *
     * @throws PromoCodeRejected
     */
    private function capture(PromoCode $promo, Company $company, User $user): void
    {
        try {
            $captured = PromoCode::query()
                ->where('id', $promo->id)
                ->whereNull('used_at')
                ->update([
                    'used_at' => now(),
                    'used_by_company_id' => $company->id,
                    'used_by_user_id' => $user->id,
                    'updated_at' => now(),
                ]);
        } catch (UniqueConstraintViolationException) {
            /*
             * Два разных кода, введённых одной компанией одновременно:
             * обе проверки assertNoRedeemedCode прошли до чужого
             * коммита, и второй захват упёрся в уникальный индекс.
             * Это отказ по правилам акции, а не ошибка сервера.
             */
            throw new PromoCodeRejected('Ваша компания уже активировала промокод — второй раз акция не действует.');
        }

        if ($captured !== 1) {
            throw new PromoCodeRejected('Этот промокод уже активирован.');
        }
    }

    /**
     * Можно ли показать компании форму ввода промокода.
     *
     * Только общее условие — «код ещё не активирован»: скидочные коды
     * доступны и платившим компаниям, поэтому прежние ограничения акции
     * с бесплатным периодом форму больше не прячут. Введёт платившая
     * компания код на бесплатный период — получит внятный отказ на поле.
     */
    public function eligible(Company $company): bool
    {
        try {
            $this->assertNoRedeemedCode($company);

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
     * Один погашенный код на компанию — правило общее для обоих видов,
     * и его же страхует уникальный индекс на used_by_company_id.
     *
     * @throws PromoCodeRejected
     */
    private function assertNoRedeemedCode(Company $company): void
    {
        $alreadyRedeemed = PromoCode::query()
            ->where('used_by_company_id', $company->id)
            ->exists();

        if ($alreadyRedeemed) {
            throw new PromoCodeRejected('Ваша компания уже активировала промокод — второй раз акция не действует.');
        }
    }

    /**
     * Условия акции с бесплатным периодом. К скидочным кодам не
     * относятся: там компания платит, и запрет «только не платившим»
     * лишал бы скидку смысла.
     *
     * @throws PromoCodeRejected
     */
    private function assertCompanyEligibleForFree(Company $company): void
    {
        /*
         * Платившая компания под акцию не подходит: бесплатный период —
         * это знакомство с платным тарифом, а не способ не платить.
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
            throw new PromoCodeRejected('Этот промокод действует только для компаний, которые ещё не оплачивали тариф.');
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
