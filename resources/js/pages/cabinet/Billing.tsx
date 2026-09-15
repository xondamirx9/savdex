import { router } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { Download, Lock, Plus, Trash2, Wallet } from 'lucide-react';
import { LimitBar, Panel, formatNumber } from '@/components/cabinet';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { BillingStore, type Invoice, type PackOffer, type PlanOffer } from '@/components/BillingStore';
import { useConfirm } from '@/components/useConfirm';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';

interface Props {
    plan: {
        name: string;
        code: string;
        price_uzs: number;
        listings_limit: number | null;
        contacts_limit: number | null;
        promo_units: number;
    } | null;
    subscription: { id: number; status: string; auto_renew: boolean; ends_at: string | null; days_left: number | null } | null;
    wallet: {
        credits: number;
        contacts_used: number;
        contacts_limit: number | null;
        promo_units: number;
        promo_limit: number;
        resets_at: string | null;
    } | null;
    cards: { id: number; masked: string; expires: string | null; provider: string; is_default: boolean }[];
    payments: { id: number; date: string; description: string; method: string; amount: number; currency: string; status: string }[];
    plans: PlanOffer[];
    packs: PackOffer[];
    /** Счета, ожидающие оплаты */
    invoices: Invoice[];
    requisites: Record<string, string>;
    /** Онлайн-касса включена: кнопки покупки ведут на страницу оплаты */
    checkout: boolean;
    /** Компания подходит под акцию с промокодом — показывать форму ввода */
    promoAllowed: boolean;
}

/* Только цвет: подпись берётся из словаря по коду статуса */
const STATUS_CLASS: Record<string, string> = {
    paid: 'badge-verified',
    pending: 'badge-neutral',
    failed: 'badge-danger',
    refunded: 'badge-neutral',
};

export default function Billing({ plan, subscription, wallet, cards, payments, plans, packs, invoices, requisites, checkout, promoAllowed }: Props) {
    const { confirm, dialog } = useConfirm();

    if (!plan || !wallet) {
        return (
            <CabinetLayout title={t('cabinet.billing.title')} heading={t('cabinet.billing.title')}>
                <div className="card empty">
                    <p className="t-h4">{t('cabinet.billing.no_company')}</p>
                    <Link href={routes.cabinetCompany} className="btn btn-primary mt-24">
                        {t('cabinet.billing.to_company')}
                    </Link>
                </div>
            </CabinetLayout>
        );
    }

    return (
        <CabinetLayout
            title={t('cabinet.billing.title')}
            heading={t('cabinet.billing.title')}
            subheading={
                subscription?.ends_at
                    ? subscription.auto_renew
                        ? t('cabinet.billing.renews', { plan: plan.name, date: subscription.ends_at })
                        : t('cabinet.billing.until', { plan: plan.name, date: subscription.ends_at })
                    : t('cabinet.billing.forever', { plan: plan.name })
            }
        >
            {dialog}

            <div className="grid grid-3 grid-tight" style={{ marginBottom: 24 }}>
                <div className="card">
                    <div className="metric-label">{t('cabinet.billing.current_plan')}</div>
                    <div className="t-h2 mt-8">{plan.name}</div>
                    <p className="t-sm muted mt-8">
                        {plan.price_uzs > 0
                            ? t('cabinet.billing.per_month', { price: formatNumber(plan.price_uzs) })
                            : t('cabinet.billing.free')}
                    </p>
                    <div className="row" style={{ gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
                        <a href="#store" className="btn btn-primary btn-sm">
                            {t('cabinet.billing.change_plan')}
                        </a>
                        {subscription &&
                            (subscription.auto_renew ? (
                                <button
                                    className="btn btn-ghost btn-sm"
                                    onClick={() =>
                                        confirm({
                                            title: t('cabinet.billing.auto_off_title'),
                                            description: t('cabinet.billing.auto_off_text'),
                                            confirmLabel: t('cabinet.billing.auto_off'),
                                            onConfirm: () =>
                                                router.post(routes.cabinetBilling + '/cancel', {}, { preserveScroll: true }),
                                        })
                                    }
                                >
                                    {t('cabinet.billing.cancel')}
                                </button>
                            ) : (
                                <button
                                    className="btn btn-secondary btn-sm"
                                    onClick={() => router.post(routes.cabinetBilling + '/resume', {}, { preserveScroll: true })}
                                >
                                    {t('cabinet.billing.resume')}
                                </button>
                            ))}
                    </div>
                </div>

                <div className="card">
                    <div className="metric-label">{t('cabinet.billing.credits')}</div>
                    <div className="metric-value mt-8">{wallet.credits}</div>
                    <p className="t-sm muted">
                        {wallet.contacts_limit === null
                            ? t('cabinet.billing.contacts_unlimited')
                            : t('cabinet.billing.contacts_used', {
                                  used: wallet.contacts_used,
                                  total: wallet.contacts_limit,
                              })}
                    </p>
                    {/* Раньше кнопка была отключена — покупать было негде.
                        Теперь пакеты продаются ниже на этой же странице */}
                    <a href="#store" className="btn btn-secondary btn-sm mt-16">
                        {t('cabinet.billing.buy_pack')}
                    </a>
                </div>

                <div className="card">
                    <div className="metric-label">{t('cabinet.billing.promo_units')}</div>
                    <div className="metric-value mt-8">{wallet.promo_units}</div>
                    <p className="t-sm muted">{t('cabinet.billing.of_month', { total: wallet.promo_limit })}</p>
                    <Link href={routes.cabinetPromo} className="btn btn-secondary btn-sm mt-16">
                        {t('cabinet.billing.spend')}
                    </Link>
                </div>
            </div>

            <Panel title={t('cabinet.billing.limits')} className="mb-24">
                <div className="stack-16">
                    <LimitBar
                        label={t('cabinet.billing.contacts_month')}
                        used={wallet.contacts_used}
                        total={wallet.contacts_limit}
                    />
                    <LimitBar
                        label={t('cabinet.billing.promo_units')}
                        used={wallet.promo_limit - wallet.promo_units}
                        total={wallet.promo_limit}
                    />
                </div>
                {wallet.resets_at && (
                    <p className="t-sm muted mt-16">
                        {t('cabinet.billing.limits_reset', { date: wallet.resets_at })}
                    </p>
                )}
            </Panel>

            {/* Покупка стоит выше карт и истории: это то, зачем сюда
                заходят, а карта и прошлые платежи — справочная часть */}
            <div id="store" className="mb-24">
                <BillingStore
                    plans={plans}
                    packs={packs}
                    invoices={invoices}
                    requisites={requisites}
                    checkout={checkout}
                    promoAllowed={promoAllowed}
                />
            </div>

            <Panel title={t('cabinet.billing.method')} className="mb-24">
                {cards.length === 0 ? (
                    <p className="muted t-sm">{t('cabinet.billing.no_card')}</p>
                ) : (
                    cards.map((card) => (
                        <div key={card.id} className="row-between card card--pad-sm wrap" style={{ gap: 12, marginBottom: 10 }}>
                            <div className="row" style={{ gap: 12 }}>
                                <span className="ico-box">
                                    <Wallet aria-hidden className="size-5" />
                                </span>
                                <span>
                                    <b>{card.masked}</b>
                                    <br />
                                    <span className="t-caption muted">
                                        {card.expires && `${t('cabinet.billing.card_until', { date: card.expires })} · `}
                                        {t('cabinet.billing.card_via', { provider: card.provider })}
                                        {card.is_default && ` · ${t('cabinet.billing.card_default')}`}
                                    </span>
                                </span>
                            </div>
                            <button
                                className="btn btn-ghost btn-icon"
                                aria-label={t('cabinet.billing.unlink_aria', { card: card.masked })}
                                onClick={() =>
                                    confirm({
                                        title: t('cabinet.billing.unlink_title', { card: card.masked }),
                                        description: t('cabinet.billing.unlink_text'),
                                        confirmLabel: t('cabinet.billing.unlink'),
                                        danger: true,
                                        onConfirm: () =>
                                            router.delete(`/cabinet/billing/card/${card.id}`, { preserveScroll: true }),
                                    })
                                }
                            >
                                <Trash2 aria-hidden className="size-5" />
                            </button>
                        </div>
                    ))
                )}

                <button className="btn btn-secondary btn-sm mt-16" disabled>
                    <Plus aria-hidden className="size-4" /> {t('cabinet.billing.link_card')}
                </button>
                <p className="hint">{t('cabinet.billing.link_card_soon')}</p>

                <div className="alert alert-info mt-16">
                    <Lock aria-hidden className="size-5" />
                    <div>{t('cabinet.billing.card_safety')}</div>
                </div>
            </Panel>

            <Panel
                title={t('cabinet.billing.history')}
                /* Раньше здесь была отключённая кнопка «Все документы»
                   без объяснения. Документ есть у каждого платежа —
                   ссылка стоит в его строке */
                action={undefined}
            >
                {payments.length === 0 ? (
                    <p className="muted t-sm">{t('cabinet.billing.history_empty')}</p>
                ) : (
                    <div className="table-wrap table-cards" style={{ border: 'none' }}>
                        <table className="table" style={{ minWidth: 0 }}>
                            <thead>
                                <tr>
                                    <th>{t('cabinet.billing.col_date')}</th>
                                    <th>{t('cabinet.billing.col_purpose')}</th>
                                    <th>{t('cabinet.billing.col_method')}</th>
                                    <th className="num">{t('cabinet.billing.col_amount')}</th>
                                    <th>{t('cabinet.billing.col_status')}</th>
                                    <th>
                                        <span className="sr-only">{t('cabinet.billing.col_document')}</span>
                                    </th>
                                </tr>
                            </thead>
                            <tbody>
                                {payments.map((p) => {
                                    const statusClass = STATUS_CLASS[p.status] ?? STATUS_CLASS.pending;
                                    return (
                                        <tr key={p.id}>
                                            <td data-label={t('cabinet.billing.col_date')}>{p.date}</td>
                                            <td data-label={t('cabinet.billing.col_purpose')}>{p.description}</td>
                                            <td data-label={t('cabinet.billing.col_method')}>{p.method}</td>
                                            <td data-label={t('cabinet.billing.col_amount')} className="num">
                                                {formatNumber(p.amount)}{' '}
                                                {p.currency === 'UZS' ? t('catalog.currency_uzs') : p.currency}
                                            </td>
                                            <td data-label={t('cabinet.billing.col_status')}>
                                                <span className={`badge ${statusClass}`}>
                                                    {t(`cabinet.billing.status_${p.status}`)}
                                                </span>
                                            </td>
                                            {/* Документ по каждому платежу: бухгалтерии
                                                нужен счёт, а не строка в списке */}
                                            <td data-label={t('cabinet.billing.col_document')}>
                                                <a
                                                    href={`/cabinet/billing/invoice/${p.id}`}
                                                    target="_blank"
                                                    rel="noopener"
                                                    className="btn btn-ghost btn-sm"
                                                >
                                                    <Download aria-hidden className="size-4" />{' '}
                                                    {t('cabinet.billing.invoice')}
                                                </a>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                )}
            </Panel>
        </CabinetLayout>
    );
}
