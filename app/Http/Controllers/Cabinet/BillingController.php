<?php

declare(strict_types=1);

namespace App\Http\Controllers\Cabinet;

use App\Http\Controllers\Controller;
use App\Models\CreditPack;
use App\Models\Payment;
use App\Models\PaymentMethod;
use App\Models\Plan;
use App\Models\Setting;
use App\Services\OrderService;
use App\Support\CurrencyRate;
use Illuminate\Contracts\View\View;
use Illuminate\Http\RedirectResponse;
use Illuminate\Http\Request;
use Inertia\Inertia;
use Inertia\Response;

/**
 * Тариф, кошелёк, карты и история платежей.
 *
 * Оплата идёт по счёту: компания заказывает тариф или пакет кредитов,
 * получает счёт с номером, платит переводом и ждёт зачисления. Так
 * покупает бизнес в Узбекистане; карточная касса (Payme, Click) станет
 * вторым способом, а не первым — место для неё оставлено в схеме.
 */
class BillingController extends Controller
{
    public function index(Request $request): Response
    {
        $company = $request->user()->company;

        if ($company === null) {
            return Inertia::render('cabinet/Billing', [
                'plan' => null,
                'subscription' => null,
                'wallet' => null,
                'cards' => [],
                'payments' => [],
                'plans' => [],
                'packs' => [],
                'invoices' => [],
                'requisites' => [],
            ]);
        }

        $plan = $company->plan();
        $subscription = $company->subscription;
        $wallet = $company->wallet;
        $rate = app(CurrencyRate::class)->usd();

        return Inertia::render('cabinet/Billing', [
            'plan' => [
                'name' => $plan->name,
                'code' => $plan->code,
                'price_uzs' => $plan->priceUzs($rate),
                'listings_limit' => $plan->listings_limit,
                'contacts_limit' => $plan->contacts_limit,
                'promo_units' => $plan->promo_units,
            ],

            'subscription' => $subscription === null ? null : [
                'id' => $subscription->id,
                'status' => $subscription->status,
                'auto_renew' => $subscription->auto_renew,
                'ends_at' => $subscription->ends_at?->translatedFormat('d.m.Y'),
                'days_left' => $subscription->ends_at?->diffInDays(now()),
            ],

            'wallet' => [
                'credits' => $wallet?->credits ?? 0,
                'contacts_used' => $wallet?->contacts_used_this_period ?? 0,
                'contacts_limit' => $plan->contacts_limit,
                'promo_units' => $wallet?->promo_units ?? 0,
                'promo_limit' => $plan->promo_units,
                'resets_at' => $wallet?->period_resets_at?->translatedFormat('d.m.Y'),
            ],

            'cards' => $company->paymentMethods()->get()->map(fn (PaymentMethod $m): array => [
                'id' => $m->id,
                'masked' => $m->masked(),
                'expires' => $m->expires,
                'provider' => $m->provider,
                'is_default' => $m->is_default,
            ]),

            'payments' => $company->payments()->with('method')->latest()->limit(20)->get()
                ->map(fn (Payment $p): array => [
                    'id' => $p->id,
                    'date' => ($p->paid_at ?? $p->created_at)->translatedFormat('d.m.Y'),
                    'description' => $p->description,
                    'method' => $p->method !== null
                        ? ucfirst((string) $p->provider).' · '.$p->method->masked()
                        : ucfirst((string) $p->provider),
                    'amount' => $p->amount,
                    'currency' => $p->currency,
                    'status' => $p->status,
                ]),

            'plans' => Plan::query()->where('is_active', true)->orderBy('sort')->get()
                ->map(fn (Plan $p): array => [
                    'id' => $p->id,
                    'code' => $p->code,
                    'name' => $p->name,
                    'price_uzs' => $p->priceUzs($rate),
                    'listings_limit' => $p->listings_limit,
                    'contacts_limit' => $p->contacts_limit,
                    'current' => $p->code === $plan->code,
                    // Бесплатный тариф не покупают: счёт на ноль сумм
                    // выглядит издевательством
                    'orderable' => $p->code !== Plan::FREE && $p->code !== $plan->code,
                ]),

            'packs' => CreditPack::query()->where('is_active', true)->orderBy('sort')->get()
                ->map(fn (CreditPack $p): array => [
                    'id' => $p->id,
                    'name' => $p->name,
                    'credits' => $p->credits,
                    'price_uzs' => $p->priceUzs($rate),
                    'per_credit' => $p->perCredit($rate),
                ]),

            /*
             * Неоплаченные счета — отдельно от истории: это дело,
             * которое ждёт покупателя, а не запись о прошлом.
             */
            'invoices' => $company->payments()
                ->where('status', 'pending')
                ->latest()
                ->get()
                ->map(fn (Payment $p): array => [
                    'id' => $p->id,
                    'number' => $p->number,
                    'description' => $p->description,
                    'amount' => $p->amountLabel(),
                    'created_at' => $p->created_at->translatedFormat('d.m.Y'),
                    'expires_at' => $p->expiresAt()?->translatedFormat('d.m.Y'),
                ]),

            'requisites' => self::requisites(),
        ]);
    }

    /**
     * Реквизиты для оплаты счёта.
     *
     * Из настроек площадки, а не из кода: банк и расчётный счёт меняются
     * без участия разработчика, и в этот момент неверные реквизиты
     * означают деньги, ушедшие не туда.
     *
     * @return array<string, string>
     */
    private static function requisites(): array
    {
        return array_filter([
            'Получатель' => (string) Setting::get('legal_name', ''),
            'ИНН' => (string) Setting::get('legal_tin', ''),
            'Расчётный счёт' => (string) Setting::get('legal_account', ''),
            'Банк' => (string) Setting::get('legal_bank', ''),
            'МФО' => (string) Setting::get('legal_mfo', ''),
        ], fn (string $v): bool => $v !== '');
    }

    /**
     * Заказ тарифа или пакета кредитов.
     *
     * Счёт создаётся сразу, доступ не выдаётся: он откроется, когда
     * деньги дойдут и администратор отметит зачисление.
     */
    public function order(Request $request): RedirectResponse
    {
        $company = $request->user()->company;

        if ($company === null) {
            return back()->with('error', 'Сначала заполните данные компании — счёт выставляется на неё');
        }

        $data = $request->validate([
            'kind' => ['required', 'in:plan,credits'],
            'id' => ['required', 'integer'],
        ]);

        /*
         * Незакрытый счёт на то же самое не выставляется повторно.
         * Иначе за день накапливается десяток счетов на один тариф,
         * и бухгалтерия обеих сторон разбирается, какой из них оплачен.
         */
        $duplicate = $company->payments()
            ->where('status', 'pending')
            ->where($data['kind'] === 'plan' ? 'plan_id' : 'credit_pack_id', $data['id'])
            ->first();

        if ($duplicate !== null) {
            return back()->with('warning', "Счёт {$duplicate->number} на это уже выставлен и ждёт оплаты");
        }

        $orders = app(OrderService::class);

        $payment = $data['kind'] === 'plan'
            ? $orders->orderPlan($company, Plan::findOrFail($data['id']), $request->user())
            : $orders->orderCredits($company, CreditPack::findOrFail($data['id']), $request->user());

        return back()->with('success', "Счёт {$payment->number} на {$payment->amountLabel()} сформирован. Реквизиты — ниже, доступ откроется после зачисления.");
    }

    /**
     * Печатная форма счёта.
     *
     * Отдельная страница вне Inertia: это документ, который несут
     * в банк и подшивают в бухгалтерию, а не экран приложения.
     * PDF делает сам браузер — серверный генератор означал бы ещё
     * одну зависимость со своими шрифтами для кириллицы и своим
     * набором отличий от того, что человек видит на экране.
     */
    public function invoice(Request $request, int $id): View
    {
        $company = $request->user()->company;

        abort_if($company === null, 404);

        $payment = $company->payments()->with(['company'])->find($id);

        abort_if($payment === null, 404);

        return view('invoice', [
            'payment' => $payment,
            'requisites' => self::requisites(),
        ]);
    }

    /** Отказ от неоплаченного счёта. */
    public function cancelInvoice(Request $request, int $id): RedirectResponse
    {
        $company = $request->user()->company;

        abort_if($company === null, 404);

        $payment = $company->payments()->where('status', 'pending')->find($id);

        abort_if($payment === null, 404);

        app(OrderService::class)->cancel($payment);

        return back()->with('success', "Счёт {$payment->number} отменён");
    }

    /**
     * Отмена автопродления.
     *
     * Подписка не обрывается сразу: оплаченный период остаётся за
     * компанией до конца. Отбирать оплаченное при отказе от продления —
     * штраф за уход, а не условие сделки.
     */
    public function cancel(Request $request): RedirectResponse
    {
        $subscription = $request->user()->company?->subscription;

        abort_if($subscription === null, 404);

        $subscription->forceFill([
            'auto_renew' => false,
            'cancelled_at' => now(),
        ])->save();

        $until = $subscription->ends_at?->translatedFormat('d.m.Y');

        return back()->with('success', $until !== null
            ? "Автопродление отключено. Тариф действует до {$until}."
            : 'Автопродление отключено.');
    }

    public function resume(Request $request): RedirectResponse
    {
        $subscription = $request->user()->company?->subscription;

        abort_if($subscription === null, 404);

        $subscription->forceFill(['auto_renew' => true, 'cancelled_at' => null])->save();

        return back()->with('success', 'Автопродление включено');
    }

    public function removeCard(Request $request, int $id): RedirectResponse
    {
        $company = $request->user()->company;

        abort_if($company === null, 404);

        $card = $company->paymentMethods()->find($id);

        abort_if($card === null, 404);

        // Без карты продлевать нечем — предупреждаем до, а не после
        if ($card->is_default && (bool) $company->subscription?->auto_renew) {
            return back()->with(
                'error',
                'Это основная карта, по ней идёт автопродление. Сначала привяжите другую или отключите автопродление.',
            );
        }

        $card->delete();

        return back()->with('success', 'Карта отвязана');
    }
}
