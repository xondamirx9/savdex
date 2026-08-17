import { router } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { Download, Lock, Plus, Trash2, Wallet } from 'lucide-react';
import { LimitBar, Panel, formatNumber } from '@/components/cabinet';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { BillingStore, type Invoice, type PackOffer, type PlanOffer } from '@/components/BillingStore';
import { useConfirm } from '@/components/useConfirm';
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
}

const STATUS_LABEL: Record<string, { label: string; cls: string }> = {
    paid: { label: 'Оплачен', cls: 'badge-verified' },
    pending: { label: 'Ожидает', cls: 'badge-neutral' },
    failed: { label: 'Не прошёл', cls: 'badge-danger' },
    refunded: { label: 'Возвращён', cls: 'badge-neutral' },
};

export default function Billing({ plan, subscription, wallet, cards, payments, plans, packs, invoices, requisites, checkout }: Props) {
    const { confirm, dialog } = useConfirm();

    if (!plan || !wallet) {
        return (
            <CabinetLayout title="Тариф и оплата" heading="Тариф и оплата">
                <div className="card empty">
                    <p className="t-h4">Сначала заполните данные компании</p>
                    <Link href={routes.cabinetCompany} className="btn btn-primary mt-24">
                        Перейти к компании
                    </Link>
                </div>
            </CabinetLayout>
        );
    }

    return (
        <CabinetLayout
            title="Тариф и оплата"
            heading="Тариф и оплата"
            subheading={
                subscription?.ends_at
                    ? subscription.auto_renew
                        ? `${plan.name} · продлевается ${subscription.ends_at}`
                        : `${plan.name} · действует до ${subscription.ends_at}, автопродление отключено`
                    : `${plan.name} · бессрочно, без списаний`
            }
        >
            {dialog}

            <div className="grid grid-3 grid-tight" style={{ marginBottom: 24 }}>
                <div className="card">
                    <div className="metric-label">Текущий тариф</div>
                    <div className="t-h2 mt-8">{plan.name}</div>
                    <p className="t-sm muted mt-8">
                        {plan.price_uzs > 0 ? `${formatNumber(plan.price_uzs)} сум / месяц` : 'бесплатно'}
                    </p>
                    <div className="row" style={{ gap: 8, marginTop: 16, flexWrap: 'wrap' }}>
                        <a href="#store" className="btn btn-primary btn-sm">
                            Сменить тариф
                        </a>
                        {subscription &&
                            (subscription.auto_renew ? (
                                <button
                                    className="btn btn-ghost btn-sm"
                                    onClick={() =>
                                        confirm({
                                            title: 'Отключить автопродление?',
                                            description:
                                                'Оплаченный период останется за вами до конца — отбирать оплаченное площадка не будет. Счёт на следующий период просто не выставится.',
                                            confirmLabel: 'Отключить',
                                            onConfirm: () =>
                                                router.post(routes.cabinetBilling + '/cancel', {}, { preserveScroll: true }),
                                        })
                                    }
                                >
                                    Отменить
                                </button>
                            ) : (
                                <button
                                    className="btn btn-secondary btn-sm"
                                    onClick={() => router.post(routes.cabinetBilling + '/resume', {}, { preserveScroll: true })}
                                >
                                    Возобновить
                                </button>
                            ))}
                    </div>
                </div>

                <div className="card">
                    <div className="metric-label">Кредиты на контакты</div>
                    <div className="metric-value mt-8">{wallet.credits}</div>
                    <p className="t-sm muted">
                        {wallet.contacts_limit === null
                            ? 'без ограничений по тарифу'
                            : `использовано ${wallet.contacts_used} из ${wallet.contacts_limit} в этом месяце`}
                    </p>
                    {/* Раньше кнопка была отключена — покупать было негде.
                        Теперь пакеты продаются ниже на этой же странице */}
                    <a href="#store" className="btn btn-secondary btn-sm mt-16">
                        Докупить пакет
                    </a>
                </div>

                <div className="card">
                    <div className="metric-label">Единицы продвижения</div>
                    <div className="metric-value mt-8">{wallet.promo_units}</div>
                    <p className="t-sm muted">из {wallet.promo_limit} в этом месяце</p>
                    <Link href={routes.cabinetPromo} className="btn btn-secondary btn-sm mt-16">
                        Потратить
                    </Link>
                </div>
            </div>

            <Panel title="Использование лимитов" className="mb-24">
                <div className="stack-16">
                    <LimitBar label="Контакты в этом месяце" used={wallet.contacts_used} total={wallet.contacts_limit} />
                    <LimitBar
                        label="Единицы продвижения"
                        used={wallet.promo_limit - wallet.promo_units}
                        total={wallet.promo_limit}
                    />
                </div>
                {wallet.resets_at && <p className="t-sm muted mt-16">Лимиты обновятся {wallet.resets_at}</p>}
            </Panel>

            {/* Покупка стоит выше карт и истории: это то, зачем сюда
                заходят, а карта и прошлые платежи — справочная часть */}
            <div id="store" className="mb-24">
                <BillingStore plans={plans} packs={packs} invoices={invoices} requisites={requisites} checkout={checkout} />
            </div>

            <Panel title="Способ оплаты" className="mb-24">
                {cards.length === 0 ? (
                    <p className="muted t-sm">
                        Карта не привязана. Она понадобится для автопродления — разовую оплату можно провести и без
                        привязки.
                    </p>
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
                                        {card.expires && `до ${card.expires} · `}
                                        привязана через {card.provider}
                                        {card.is_default && ' · основная'}
                                    </span>
                                </span>
                            </div>
                            <button
                                className="btn btn-ghost btn-icon"
                                aria-label={`Отвязать карту ${card.masked}`}
                                onClick={() =>
                                    confirm({
                                        title: `Отвязать карту ${card.masked}?`,
                                        description: 'Автопродление без привязанной карты работать не будет.',
                                        confirmLabel: 'Отвязать',
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
                    <Plus aria-hidden className="size-4" /> Привязать карту
                </button>
                <p className="hint">
                    Привязка карт появится вместе с подключением Payme. Сейчас оплата идёт по счёту:
                    выставьте его выше и оплатите переводом.
                </p>

                <div className="alert alert-info mt-16">
                    <Lock aria-hidden className="size-5" />
                    <div>
                        Номер карты не хранится на площадке — сохраняется только защищённый токен платёжной системы.
                        Автопродление отключается в один клик.
                    </div>
                </div>
            </Panel>

            <Panel
                title="История платежей"
                /* Раньше здесь была отключённая кнопка «Все документы»
                   без объяснения. Документ есть у каждого платежа —
                   ссылка стоит в его строке */
                action={undefined}
            >
                {payments.length === 0 ? (
                    <p className="muted t-sm">Платежей пока не было.</p>
                ) : (
                    <div className="table-wrap table-cards" style={{ border: 'none' }}>
                        <table className="table" style={{ minWidth: 0 }}>
                            <thead>
                                <tr>
                                    <th>Дата</th>
                                    <th>Назначение</th>
                                    <th>Способ</th>
                                    <th className="num">Сумма</th>
                                    <th>Статус</th>
                                    <th><span className="sr-only">Документ</span></th>
                                </tr>
                            </thead>
                            <tbody>
                                {payments.map((p) => {
                                    const status = STATUS_LABEL[p.status] ?? STATUS_LABEL.pending;
                                    return (
                                        <tr key={p.id}>
                                            <td data-label="Дата">{p.date}</td>
                                            <td data-label="Назначение">{p.description}</td>
                                            <td data-label="Способ">{p.method}</td>
                                            <td data-label="Сумма" className="num">
                                                {formatNumber(p.amount)} {p.currency === 'UZS' ? 'сум' : p.currency}
                                            </td>
                                            <td data-label="Статус">
                                                <span className={`badge ${status.cls}`}>{status.label}</span>
                                            </td>
                                            {/* Документ по каждому платежу: бухгалтерии
                                                нужен счёт, а не строка в списке */}
                                            <td data-label="Документ">
                                                <a
                                                    href={`/cabinet/billing/invoice/${p.id}`}
                                                    target="_blank"
                                                    rel="noopener"
                                                    className="btn btn-ghost btn-sm"
                                                >
                                                    <Download aria-hidden className="size-4" /> Счёт
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
