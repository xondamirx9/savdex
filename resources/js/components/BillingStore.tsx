import { router } from '@inertiajs/react';
import { Check, FileText, X } from 'lucide-react';
import { formatNumber } from '@/components/cabinet';
import { useConfirm } from '@/components/useConfirm';

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

    return value === null ? 'без ограничений' : String(value);
}

function order(kind: 'plan' | 'credits', id: number) {
    router.post('/cabinet/billing/order', { kind, id }, { preserveScroll: true });
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
}: {
    plans: PlanOffer[];
    packs: PackOffer[];
    /** Счета, ожидающие оплаты: дело покупателя, а не история */
    invoices: Invoice[];
    requisites: Record<string, string>;
    /** Онлайн-касса включена: кнопки ведут на страницу оплаты */
    checkout: boolean;
}) {
    const orderLabel = checkout ? 'Оплатить' : 'Выставить счёт';
    const { confirm, dialog } = useConfirm();

    return (
        <>
            {dialog}

            {invoices.length > 0 && (
                <Panel title="Счета к оплате">
                    <div className="stack-16">
                        {invoices.map((inv) => (
                            <div key={inv.id} className="card" style={{ background: 'var(--bg)' }}>
                                <div className="row-between wrap" style={{ gap: 12 }}>
                                    <div style={{ minWidth: 0 }}>
                                        <div className="row" style={{ gap: 8, alignItems: 'center' }}>
                                            <FileText aria-hidden className="size-4" />
                                            <b>{inv.number}</b>
                                            <span className="badge badge-neutral">ожидает оплаты</span>
                                        </div>
                                        <p className="t-sm mt-8">{inv.description}</p>
                                        <p className="t-xs">
                                            выставлен {inv.created_at}
                                            {inv.expires_at && ` · оплатить до ${inv.expires_at}`}
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
                                                Оплатить
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
                                            <FileText aria-hidden className="size-4" /> Счёт
                                        </a>
                                        <button
                                            className="btn btn-ghost btn-sm"
                                            onClick={() =>
                                                confirm({
                                                    title: `Отменить счёт ${inv.number}?`,
                                                    description:
                                                        'Счёт останется в истории со статусом «Отменён». Если деньги уже отправлены, отменять его не нужно — дождитесь зачисления.',
                                                    confirmLabel: 'Отменить счёт',
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
                                            <X aria-hidden className="size-4" /> Отменить
                                        </button>
                                    </div>
                                </div>
                            </div>
                        ))}
                    </div>

                    {Object.keys(requisites).length > 0 && (
                        <div className="card mt-16" style={{ background: 'var(--primary-50)', borderColor: 'var(--primary-100)' }}>
                            <p className="t-sm">
                                <b>Куда платить.</b> В назначении платежа укажите номер счёта — по нему поступление
                                находят и зачисляют.
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

            <div className="grid grid-2 grid-tight mt-24">
                <Panel title="Тарифы">
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
                                                    <Check aria-hidden className="size-3.5" /> ваш тариф
                                                </span>
                                            </>
                                        )}
                                        <p className="t-xs">
                                            объявлений: {limit(p.listings_limit, p.code)} · контактов:{' '}
                                            {limit(p.contacts_limit, p.code)} · откликов:{' '}
                                            {limit(p.responses_limit, p.code)}
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
                                            {p.price_uzs > 0 ? `${formatNumber(p.price_uzs)} сум` : 'бесплатно'}
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

                <Panel title="Пакеты контактов">
                    <p className="t-sm muted" style={{ marginBottom: 16 }}>
                        Кредиты тратятся, когда исчерпан месячный лимит тарифа. Не сгорают и не имеют срока.
                    </p>
                    <div className="stack-16">
                        {packs.map((p) => (
                            <div key={p.id} className="card" style={{ background: 'var(--bg)' }}>
                                <div className="row-between wrap" style={{ gap: 12, alignItems: 'flex-start' }}>
                                    <div style={{ minWidth: 0 }}>
                                        <b>{p.name}</b>
                                        <p className="t-xs">{formatNumber(p.per_credit)} сум за контакт</p>
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
                                        <b className="t-num nowrap">{formatNumber(p.price_uzs)} сум</b>
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
