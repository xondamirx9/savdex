import { router, useForm } from '@inertiajs/react';
import { CalendarPlus, CheckCircle2, Eye, Gavel, Pencil, Plus, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { Empty } from '@/components/cabinet';
import { Modal } from '@/components/Modal';
import { Link } from '@/components/ui/Link';
import { useConfirm } from '@/components/useConfirm';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';

interface Row {
    id: number;
    slug: string | null;
    title: string;
    customer: string | null;
    budget: string | null;
    deadline: string | null;
    /** Дней до срока у тендера на витрине */
    days_left: number | null;
    status: 'draft' | 'published' | 'archived' | 'expired';
    status_label: string;
    outcome: Outcome | null;
    outcome_label: string | null;
    outcome_party: string | null;
    outcome_amount: string | null;
    views: number;
    published: string | null;
}

type Outcome = 'contract' | 'no_deal' | 'cancelled';

const OUTCOMES: Outcome[] = ['contract', 'no_deal', 'cancelled'];

const STATUS_BADGE: Record<Row['status'], string> = {
    draft: 'badge-neutral',
    published: 'badge-verified',
    archived: 'badge-neutral',
    expired: 'badge-warning',
};

/** «Продлить»: на сколько дней — кнопками, без лишнего шага */
function ExtendModal({ tender, days, onClose }: { tender: Row; days: number[]; onClose: () => void }) {
    const [busy, setBusy] = useState(false);

    function extend(n: number) {
        setBusy(true);
        router.post(
            routes.tenderExtend(tender.id),
            { days: n },
            { preserveScroll: true, onFinish: () => setBusy(false), onSuccess: onClose },
        );
    }

    return (
        <Modal open onClose={onClose} title={t('cabinet.tenders.extend_title')} description={tender.title} width={420}>
            <p className="t-sm muted" style={{ marginBottom: 12 }}>
                {t('cabinet.tenders.extend_text')}
            </p>
            <div className="row wrap" style={{ gap: 8 }}>
                {days.map((n) => (
                    <button key={n} type="button" className="btn btn-secondary" disabled={busy} onClick={() => extend(n)}>
                        {t('cabinet.tenders.extend_days', { days: n })}
                    </button>
                ))}
            </div>
        </Modal>
    );
}

/** «Завершить»: чем закончился тендер — в архив с итогом */
function FinishModal({ tender, onClose }: { tender: Row; onClose: () => void }) {
    const form = useForm<{ outcome: Outcome | ''; party: string; amount: string }>({
        outcome: '',
        party: '',
        amount: '',
    });

    function submit() {
        form.post(routes.tenderFinish(tender.id), { preserveScroll: true, onSuccess: onClose });
    }

    return (
        <Modal
            open
            onClose={onClose}
            title={t('cabinet.tenders.finish_title')}
            description={t('cabinet.tenders.finish_text')}
            width={460}
        >
            <div style={{ display: 'grid', gap: 8, marginBottom: 12 }}>
                {OUTCOMES.map((o) => (
                    <label key={o} className="row" style={{ gap: 8 }}>
                        <input
                            type="radio"
                            name="outcome"
                            checked={form.data.outcome === o}
                            onChange={() => form.setData('outcome', o)}
                        />
                        <span>{t(`cabinet.tenders.outcomes.${o}`)}</span>
                    </label>
                ))}
                {form.errors.outcome && <p className="hint" style={{ color: 'var(--danger)' }}>{form.errors.outcome}</p>}
            </div>

            {form.data.outcome === 'contract' && (
                <>
                    <div className="field">
                        <label className="label" htmlFor="fin-party">
                            {t('cabinet.tenders.outcome_party')}
                        </label>
                        <input
                            id="fin-party"
                            className="input"
                            maxLength={190}
                            value={form.data.party}
                            onChange={(e) => form.setData('party', e.target.value)}
                        />
                        <p className="hint">{t('cabinet.tenders.outcome_party_hint')}</p>
                    </div>
                    <div className="field">
                        <label className="label" htmlFor="fin-amount">
                            {t('cabinet.tenders.outcome_amount')}
                        </label>
                        <input
                            id="fin-amount"
                            className="input"
                            inputMode="decimal"
                            value={form.data.amount}
                            onChange={(e) => form.setData('amount', e.target.value.replace(/[^\d.,]/g, '').replace(',', '.'))}
                        />
                        {form.errors.amount && <p className="hint" style={{ color: 'var(--danger)' }}>{form.errors.amount}</p>}
                    </div>
                </>
            )}

            <div className="row" style={{ gap: 10, justifyContent: 'flex-end', marginTop: 16 }}>
                <button type="button" className="btn btn-secondary" onClick={onClose}>
                    {t('common.cancel')}
                </button>
                <button
                    type="button"
                    className="btn btn-primary"
                    disabled={form.data.outcome === '' || form.processing}
                    onClick={submit}
                >
                    {t('cabinet.tenders.finish')}
                </button>
            </div>
        </Modal>
    );
}

/**
 * Свои тендеры: на витрине — «Продлить» и «Завершить», истёкший можно
 * продлить, завершённый — открыть снова
 */
export default function TendersIndex({
    tenders,
    hasCompany,
    extendDays,
}: {
    tenders: Row[];
    hasCompany: boolean;
    extendDays: number[];
}) {
    const { confirm, dialog } = useConfirm();
    const [extending, setExtending] = useState<Row | null>(null);
    const [finishing, setFinishing] = useState<Row | null>(null);

    return (
        <CabinetLayout
            title={t('cabinet.tenders.title')}
            heading={t('cabinet.tenders.title')}
            subheading={t('cabinet.tenders.subtitle')}
            actions={
                hasCompany ? (
                    <Link href={routes.tenderCreate} className="btn btn-primary btn-sm">
                        <Plus aria-hidden className="size-4" /> {t('cabinet.tenders.new')}
                    </Link>
                ) : undefined
            }
        >
            {dialog}
            {extending && <ExtendModal tender={extending} days={extendDays} onClose={() => setExtending(null)} />}
            {finishing && <FinishModal tender={finishing} onClose={() => setFinishing(null)} />}

            {tenders.length === 0 ? (
                hasCompany ? (
                    <Empty
                        icon={Gavel}
                        title={t('cabinet.tenders.empty')}
                        text={t('cabinet.tenders.empty_text')}
                        action={{ href: routes.tenderCreate, label: t('cabinet.tenders.new') }}
                    />
                ) : (
                    <Empty
                        icon={Gavel}
                        title={t('cabinet.tenders.no_company')}
                        text={t('cabinet.tenders.no_company_text')}
                        action={{ href: routes.cabinetCompany, label: t('cabinet.tenders.fill_profile') }}
                    />
                )
            ) : (
                <div style={{ display: 'grid', gap: 12 }}>
                    {tenders.map((tender) => (
                        <div key={tender.id} className="card" style={{ display: 'grid', gap: 10 }}>
                            <div className="row wrap" style={{ gap: 8, justifyContent: 'space-between' }}>
                                <div className="row wrap" style={{ gap: 8 }}>
                                    <span className={`badge ${STATUS_BADGE[tender.status] ?? 'badge-neutral'}`}>
                                        {tender.status_label}
                                    </span>
                                    {tender.published && <span className="t-caption muted">{tender.published}</span>}
                                </div>
                                <div className="row wrap" style={{ gap: 6 }}>
                                    {tender.status === 'published' && tender.slug && (
                                        <Link href={routes.tender(tender.slug)} className="btn btn-ghost btn-sm">
                                            <Eye aria-hidden className="size-4" /> {t('cabinet.tenders.on_site')}
                                        </Link>
                                    )}
                                    <Link href={routes.tenderEdit(tender.id)} className="btn btn-secondary btn-sm">
                                        <Pencil aria-hidden className="size-4" /> {t('common.edit')}
                                    </Link>
                                    {(tender.status === 'published' || tender.status === 'expired') && (
                                        <>
                                            <button
                                                type="button"
                                                className="btn btn-ghost btn-sm"
                                                onClick={() => setExtending(tender)}
                                            >
                                                <CalendarPlus aria-hidden className="size-4" /> {t('cabinet.tenders.extend')}
                                            </button>
                                            <button
                                                type="button"
                                                className="btn btn-ghost btn-sm"
                                                onClick={() => setFinishing(tender)}
                                            >
                                                <CheckCircle2 aria-hidden className="size-4" /> {t('cabinet.tenders.finish')}
                                            </button>
                                        </>
                                    )}
                                    {tender.status === 'archived' && (
                                        <button
                                            type="button"
                                            className="btn btn-ghost btn-sm"
                                            onClick={() => router.post(routes.tenderReopen(tender.id), {}, { preserveScroll: true })}
                                        >
                                            {t('cabinet.tenders.reopen')}
                                        </button>
                                    )}
                                    <button
                                        type="button"
                                        className="btn btn-ghost btn-sm"
                                        aria-label={t('common.delete')}
                                        onClick={() =>
                                            confirm({
                                                title: t('cabinet.tenders.delete_title'),
                                                description: t('cabinet.tenders.delete_text'),
                                                confirmLabel: t('common.delete'),
                                                danger: true,
                                                onConfirm: () =>
                                                    router.delete(routes.tenderUpdate(tender.id), { preserveScroll: true }),
                                            })
                                        }
                                    >
                                        <Trash2 aria-hidden className="size-4" />
                                    </button>
                                </div>
                            </div>

                            <h3 className="t-h4">{tender.title}</h3>

                            <div className="row wrap t-sm muted" style={{ gap: 16 }}>
                                {tender.customer && <span>{tender.customer}</span>}
                                {tender.budget && (
                                    <span>
                                        {t('cabinet.tenders.budget')} <b style={{ color: 'var(--text)' }}>{tender.budget}</b>
                                    </span>
                                )}
                                {tender.deadline && <span>{t('cabinet.tenders.deadline', { date: tender.deadline })}</span>}
                                {tender.days_left !== null && (
                                    <b style={{ color: tender.days_left <= 3 ? 'var(--danger)' : 'var(--text)' }}>
                                        {tender.days_left === 0
                                            ? t('cabinet.tenders.expires_today')
                                            : t('cabinet.tenders.days_left', { days: tender.days_left })}
                                    </b>
                                )}
                                <span className="row" style={{ gap: 4 }}>
                                    <Eye aria-hidden className="size-4" /> {tender.views}
                                </span>
                            </div>

                            {tender.status === 'draft' && <p className="hint">{t('cabinet.tenders.moderated')}</p>}
                            {tender.status === 'expired' && <p className="hint">{t('cabinet.tenders.expired_hint')}</p>}
                            {tender.outcome_label && (
                                <p className="t-sm">
                                    <b>{tender.outcome_label}</b>
                                    {tender.outcome_party && ` · ${tender.outcome_party}`}
                                    {tender.outcome_amount && ` · ${tender.outcome_amount}`}
                                </p>
                            )}
                        </div>
                    ))}
                </div>
            )}
        </CabinetLayout>
    );
}
