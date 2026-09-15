import { router, useForm } from '@inertiajs/react';
import { Check, FileText, Ticket, X } from 'lucide-react';
import type { FormEvent } from 'react';
import { formatNumber } from '@/components/cabinet';
import { useConfirm } from '@/components/useConfirm';
import { TextInput } from '@/components/ui';
import { t } from '@/lib/i18n';

export interface PlanOffer {
    id: number;
    code: string;
    name: string;
    price_uzs: number;
    listings_limit: number | null;
    contacts_limit: number | null;
    responses_limit: number | null;
    current: boolean;
    orderable: boolean;
}

export interface PackOffer {
    id: number;
    name: string;
    credits: number;
    price_uzs: number;
    per_credit: number;
}

export interface Invoice {
    id: number;
    number: string;
    description: string;
    amount: string;
    created_at: string;
    expires_at: string | null;
}

/** У тарифа VIP безлимит подписан словом «VIP», у остальных — как есть. */
function limit(value: number | null, code?: string): string {
    if (code === 'vip') return 'VIP';

    return value === null ? t('cabinet.common.unlimited') : String(value);
}

function order(kind: 'plan' | 'credits', id: number) {
    router.post('/cabinet/billing/order', { kind, id }, { preserveScroll: true });
}

/**
 * Ввод промокода. Кодов два вида, и различает их сервер: код на
 * бесплатный период подключает тариф сразу, скидочный выставляет
 * счёт на остаток цены и уводит на онлайн-оплату (внешний редирект
 * приходит как Inertia::location — форма его отработает сама).
 *
 * Стоит перед списком тарифов: человек с промокодом в руках приходит
 * сюда именно за ним, и искать поле под ценами ему незачем. Ошибка
 * приходит с сервера на поле — причин отказа несколько (код погашен,
 * просрочен, не тот вид), и человек должен видеть свою.
 */
function PromoCodeForm() {
    const form = useForm({ promo_code: '' });

    function submit(e: FormEvent) {
        e.preventDefault();
        form.post('/cabinet/billing/promo', {
            preserveScroll: true,
            onSuccess: () => form.reset('promo_code'),
        });
    }

    return (
        <Panel title={t('cabinet.billing.promo_title')}>
            <p className="t-sm muted" style={{ marginBottom: 16 }}>
                {t('cabinet.billing.promo_text')}
            </p>
            <form onSubmit={submit} className="row wrap" style={{ gap: 12, alignItems: 'flex-start' }}>
                <div style={{ flex: '1 1 220px', minWidth: 0 }}>
                    <TextInput
                        label={t('cabinet.billing.promo_title')}
                        name="promo_code"
                        placeholder="SVDX-XXXXXXXX"
                        autoComplete="off"
                        spellCheck={false}
                        maxLength={32}
                        value={form.data.promo_code}
                        onChange={(e) => form.setData('promo_code', e.target.value.toUpperCase())}
                        error={form.errors.promo_code}
                    />
                </div>
                <button
                    type="submit"
                    className="btn btn-primary"
                    style={{ marginTop: 26 }}
                    disabled={form.processing || form.data.promo_code.trim() === ''}
                >
                    <Ticket aria-hidden className="size-4" />
                    {form.processing ? t('cabinet.billing.promo_checking') : t('cabinet.billing.promo_apply')}
                </button>
            </form>
        </Panel>
    );
}

/**
 * Покупка тарифа и кредитов, неоплаченные счета и реквизиты.
 *
 * Два режима, выбирает сервер флагом checkout. Пока онлайн-кассы нет —
 * «Выставить счёт»: компания платит переводом и ждёт зачисления, и это
 * честнее, чем форма карты, за которой ничего не стоит. С включённой
 * кассой кнопка становится «Оплатить» и уводит на страницу провайдера;
 * счёт при этом всё равно создаётся — переводом платить не запрещали.
 */
export function BillingStore({
    plans,
    packs,
    invoices,
    requisites,
    checkout,
    promoAllowed = false,
}: {
    plans: PlanOffer[];
    packs: PackOffer[];
    /** Счета, ожидающие оплаты: дело покупателя, а не история */
    invoices: Invoice[];
    requisites: Record<string, string>;
    /** Онлайн-касса включена: кнопки ведут на страницу оплаты */
    checkout: boolean;
    /** Показывать форму промокода: код не активирован либо скидочный ещё не оплачен */
    promoAllowed?: boolean;
}) {
    const orderLabel = checkout ? t('cabinet.billing.pay') : t('cabinet.billing.invoice_me');
    const { confirm, dialog } = useConfirm();

    return (
        <>
            {dialog}

            {invoices.length > 0 && (
                <Panel title={t('cabinet.billing.due_title')}>
                    <div className="stack-16">
                        {invoices.map((inv) => (
                            <div key={inv.id} className="card" style={{ background: 'var(--bg)' }}>
                                <div className="row-between wrap" style={{ gap: 12 }}>
                                    <div style={{ minWidth: 0 }}>
                                        <div className="row" style={{ gap: 8, alignItems: 'center' }}>
                                            <FileText aria-hidden className="size-4" />
                                            <b>{inv.number}</b>
                                            <span className="badge badge-neutral">{t('cabinet.billing.awaiting')}</span>
                                        </div>
                                        <p className="t-sm mt-8">{inv.description}</p>
                                        <p className="t-xs">
                                            {t('cabinet.billing.issued', { date: inv.created_at })}
                                            {inv.expires_at &&
                                                ` · ${t('cabinet.billing.pay_until', { date: inv.expires_at })}`}
                                        </p>
                                    </div>
                                    <div className="row" style={{ gap: 10, alignItems: 'center' }}>
                                        <b className="t-num">{inv.amount}</b>
                                        {/* Онлайн-оплата уже выставленного счёта:
                                            увод на страницу платёжного провайдера */}
                                        {checkout && (
                                            <button
                                                className="btn btn-primary btn-sm"
                                                onClick={() =>
                                                    router.post(
                                                        `/cabinet/billing/invoice/${inv.id}/pay`,
                                                        {},
                                                        { preserveScroll: true },
                                                    )
                                                }
                                            >
                                                {t('cabinet.billing.pay')}
                                            </button>
                                        )}
                                        {/* Печатная форма: её несут в банк или
                                            сохраняют в PDF средствами браузера */}
                                        <a
                                            href={`/cabinet/billing/invoice/${inv.id}`}
                                            target="_blank"
                                            rel="noopener"
                                            className="btn btn-secondary btn-sm"
                                        >
                                            <FileText aria-hidden className="size-4" /> {t('cabinet.billing.invoice')}
                                        </a>
                                        <button
                                            className="btn btn-ghost btn-sm"
                                            onClick={() =>
                                                confirm({
                                                    title: t('cabinet.billing.cancel_title', {
                                                        number: inv.number,
                                                    }),
                                                    description: t('cabinet.billing.cancel_text'),
                                                    confirmLabel: t('cabinet.billing.cancel_confirm'),
                                                    danger: true,
                                                    onConfirm: () =>
                                                        router.post(
                                                            `/cabinet/billing/invoice/${inv.id}/cancel`,
                                                            {},
                                                            { preserveScroll: true },
                                                        ),
                                                })
                                            }
                                        >
                                            <X aria-hidden className="size-4" /> {t('cabinet.billing.cancel')}
                                        </button>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>

                    {Object.keys(requisites).length > 0 && (
                        <div className="card mt-16" style={{ background: 'var(--primary-50)', borderColor: 'var(--primary-100)' }}>
                            <p className="t-sm">
                                <b>{t('cabinet.billing.where_title')}</b> {t('cabinet.billing.where_text')}
                            </p>
                            <dl className="mt-12">
                                {Object.entries(requisites).map(([label, value]) => (
                                    <div key={label} className="row-between t-sm" style={{ padding: '4px 0' }}>
                                        <span className="muted">{label}</span>
                                        <span className="t-num">{value}</span>
                                    </div>
                                ))}
                            </dl>
                        </div>
                    )}
                </Panel>
            )}

            {/* Промокод показывается, пока компания не активировала код:
                скидочные коды доступны и платившим клиентам, поэтому
                форму прячет только уже погашенный промокод */}
            {promoAllowed && (
                <div className="mt-24">
                    <PromoCodeForm />
                </div>
            )}

            <div className="grid grid-2 grid-tight mt-24">
                <Panel title={t('cabinet.billing.plans')}>
                    <div className="stack-16">
                        {plans.map((p) => (
                            <div
                                key={p.id}
                                className="card"
                                style={{
                                    background: p.current ? 'var(--primary-50)' : 'var(--bg)',
                                    borderColor: p.current ? 'var(--primary-100)' : undefined,
                                }}
                            >
                                <div className="row-between wrap" style={{ gap: 12, alignItems: 'flex-start' }}>
                                    <div style={{ minWidth: 0 }}>
                                        <b>{p.name}</b>
                                        {p.current && (
                                            <>
                                                {' '}
                                                <span className="badge badge-verified">
                                                    <Check aria-hidden className="size-3.5" />{' '}
                                                    {t('cabinet.billing.your_plan')}
                                                </span>
                                            </>
                                        )}
                                        <p className="t-xs">
                                            {t('cabinet.billing.plan_limits', {
                                                listings: limit(p.listings_limit, p.code),
                                                contacts: limit(p.contacts_limit, p.code),
                                                responses: limit(p.responses_limit, p.code),
                                            })}
                                        </p>
                                    </div>
                                    {/* Цена над кнопкой, а не в одну строку с ней:
                                        инлайновая пара слипалась в «107 000 сум[кнопка]» */}
                                    <div
                                        style={{
                                            display: 'flex',
                                            flexDirection: 'column',
                                            alignItems: 'flex-end',
                                            gap: 8,
                                            textAlign: 'right',
                                        }}
                                    >
                                        <b className="t-num nowrap">
                                            {p.price_uzs > 0
                                                ? `${formatNumber(p.price_uzs)} ${t('catalog.currency_uzs')}`
                                                : t('cabinet.billing.free')}
                                        </b>
                                        {p.orderable && (
                                            <button
                                                className="btn btn-primary btn-sm"
                                                onClick={() => order('plan', p.id)}
                                            >
                                                {orderLabel}
                                            </button>
                                        )}
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </Panel>

                <Panel title={t('cabinet.billing.packs')}>
                    <p className="t-sm muted" style={{ marginBottom: 16 }}>
                        {t('cabinet.billing.packs_text')}
                    </p>
                    <div className="stack-16">
                        {packs.map((p) => (
                            <div key={p.id} className="card" style={{ background: 'var(--bg)' }}>
                                <div className="row-between wrap" style={{ gap: 12, alignItems: 'flex-start' }}>
                                    <div style={{ minWidth: 0 }}>
                                        <b>{p.name}</b>
                                        <p className="t-xs">
                                            {t('cabinet.billing.per_contact', {
                                                price: formatNumber(p.per_credit),
                                            })}
                                        </p>
                                    </div>
                                    <div
                                        style={{
                                            display: 'flex',
                                            flexDirection: 'column',
                                            alignItems: 'flex-end',
                                            gap: 8,
                                            textAlign: 'right',
                                        }}
                                    >
                                        <b className="t-num nowrap">
                                            {formatNumber(p.price_uzs)} {t('catalog.currency_uzs')}
                                        </b>
                                        <button
                                            className="btn btn-secondary btn-sm"
                                            onClick={() => order('credits', p.id)}
                                        >
                                            {orderLabel}
                                        </button>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>
                </Panel>
            </div>
        </>
    );
}

/** Локальная обёртка-панель: у общей другой набор пропсов. */
function Panel({ title, children }: { title: string; children: React.ReactNode }) {
    return (
        <section className="card">
            <h2 className="t-h4" style={{ marginBottom: 16 }}>
                {title}
            </h2>
            {children}
        </section>
    );
}
