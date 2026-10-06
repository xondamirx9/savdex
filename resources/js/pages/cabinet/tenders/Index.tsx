import { router } from '@inertiajs/react';
import { Eye, Gavel, Pencil, Plus, Trash2 } from 'lucide-react';
import { Empty } from '@/components/cabinet';
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
    status: 'draft' | 'published' | 'archived';
    status_label: string;
    views: number;
    published: string | null;
}

const STATUS_BADGE: Record<Row['status'], string> = {
    draft: 'badge-neutral',
    published: 'badge-verified',
    archived: 'badge-neutral',
};

/** Свои тендеры: открытые — на витрине, закрытые можно открыть снова */
export default function TendersIndex({ tenders, hasCompany }: { tenders: Row[]; hasCompany: boolean }) {
    const { confirm, dialog } = useConfirm();

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
                                    {tender.status === 'published' && (
                                        <button
                                            type="button"
                                            className="btn btn-ghost btn-sm"
                                            onClick={() =>
                                                confirm({
                                                    title: t('cabinet.tenders.close_title'),
                                                    description: t('cabinet.tenders.close_text'),
                                                    confirmLabel: t('cabinet.tenders.close'),
                                                    onConfirm: () =>
                                                        router.post(routes.tenderClose(tender.id), {}, { preserveScroll: true }),
                                                })
                                            }
                                        >
                                            {t('cabinet.tenders.close')}
                                        </button>
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
                                <span className="row" style={{ gap: 4 }}>
                                    <Eye aria-hidden className="size-4" /> {tender.views}
                                </span>
                            </div>

                            {tender.status === 'draft' && <p className="hint">{t('cabinet.tenders.moderated')}</p>}
                        </div>
                    ))}
                </div>
            )}
        </CabinetLayout>
    );
}
