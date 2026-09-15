import { Link } from '@/components/ui/Link';
import { BadgeCheck, Eye, Lock, PhoneCall } from 'lucide-react';
import type { ReactNode } from 'react';
import { Empty } from '@/components/cabinet';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { routes } from '@/routes';
import { t, tChoice } from '@/lib/i18n';

interface Row {
    id: number;
    name: string | null;
    slug: string | null;
    initials: string | null;
    verified: number;
    type: string;
    rating: number;
    city: string;
    listing: string | null;
    when: string;
}

interface ViewerRow {
    id: number;
    name: string | null;
    slug: string | null;
    initials: string | null;
    verified: number;
    type: string;
    rating: number;
    city: string;
    looked: string;
    views: number;
    when: string;
}

/** Ячейка «Компания»: имя за тарифным замком, тип и рейтинг всегда. */
function CompanyCell({
    row,
    seesNames,
}: {
    row: { name: string | null; slug: string | null; initials: string | null; verified: number; type: string; rating: number };
    seesNames: boolean;
}) {
    return (
        <div className="row" style={{ gap: 10 }}>
            <span className="listing-logo logo-32">
                {seesNames ? row.initials : <Lock aria-hidden className="size-3.5" />}
            </span>
            <span style={{ minWidth: 0 }}>
                {seesNames ? (
                    <>
                        <b>{row.slug ? <Link href={routes.company(row.slug)}>{row.name}</Link> : (row.name ?? t('cabinet.incoming.deleted'))}</b>
                        {row.verified > 0 && (
                            <>
                                {' '}
                                <span className="badge badge-verified">
                                    <BadgeCheck aria-hidden className="size-3.5" />
                                </span>
                            </>
                        )}
                    </>
                ) : (
                    <b className="muted">{t('cabinet.incoming.hidden')}</b>
                )}
                <br />
                <span className="t-caption muted">
                    {row.type}
                    {row.rating > 0 && ` · ${t('cabinet.incoming.rating', { value: row.rating.toFixed(1) })}`}
                </span>
            </span>
        </div>
    );
}

function Section({ icon: Icon, title, hint, children }: { icon: typeof Eye; title: string; hint: string; children: ReactNode }) {
    return (
        <section className="card mt-24">
            <div className="row" style={{ gap: 10, marginBottom: 6 }}>
                <span className="ico-box ico-box-sm shrink-0">
                    <Icon aria-hidden className="size-4" />
                </span>
                <div>
                    <h2 className="t-h3">{title}</h2>
                    <p className="t-caption muted">{hint}</p>
                </div>
            </div>
            {children}
        </section>
    );
}

export default function Incoming({
    rows,
    viewers,
    sees_names,
    plan,
}: {
    rows: Row[];
    viewers: ViewerRow[];
    sees_names: boolean;
    plan: { name: string } | null;
}) {
    return (
        <CabinetLayout
            title={t('cabinet.incoming.title')}
            heading={t('cabinet.incoming.title')}
            subheading={t('cabinet.incoming.subheading')}
        >
            {rows.length === 0 && viewers.length === 0 ? (
                <Empty
                    icon={Eye}
                    title={t('cabinet.incoming.empty_title')}
                    text={t('cabinet.incoming.empty_text')}
                    action={{ href: routes.cabinetListings, label: t('cabinet.incoming.empty_action') }}
                />
            ) : (
                <>
                    {rows.length > 0 && (
                        <Section
                            icon={PhoneCall}
                            title={t('cabinet.incoming.unlocked_title')}
                            hint={t('cabinet.incoming.unlocked_hint')}
                        >
                            <div className="table-wrap table-cards">
                                <table className="table">
                                    <thead>
                                        <tr>
                                            <th>{t('cabinet.incoming.company')}</th>
                                            <th>{t('cabinet.incoming.listing')}</th>
                                            <th>{t('cabinet.incoming.when')}</th>
                                            <th>{t('cabinet.incoming.city')}</th>
                                            <th>
                                                <span className="sr-only">{t('cabinet.incoming.actions')}</span>
                                            </th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {rows.map((row) => (
                                            <tr key={row.id}>
                                                <td data-label={t('cabinet.incoming.company')}>
                                                    <CompanyCell row={row} seesNames={sees_names} />
                                                </td>
                                                <td data-label={t('cabinet.incoming.listing')}>
                                                    <span className="t-sm">{row.listing ?? '—'}</span>
                                                </td>
                                                <td data-label={t('cabinet.incoming.when')}>{row.when}</td>
                                                <td data-label={t('cabinet.incoming.city')}>{row.city}</td>
                                                <td data-label="">
                                                    {sees_names && row.slug ? (
                                                        <Link href={routes.company(row.slug)} className="btn btn-secondary btn-sm">
                                                    {t('cabinet.incoming.write_first')}
                                                        </Link>
                                                    ) : (
                                                        <span className="t-caption muted">—</span>
                                                    )}
                                                </td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </Section>
                    )}

                    {viewers.length > 0 && (
                        <Section
                            icon={Eye}
                            title={t('cabinet.incoming.viewed_title')}
                            hint={t('cabinet.incoming.viewed_hint')}
                        >
                            <div className="table-wrap table-cards">
                                <table className="table">
                                    <thead>
                                        <tr>
                                            <th>{t('cabinet.incoming.company')}</th>
                                            <th>{t('cabinet.incoming.what_viewed')}</th>
                                            <th>{t('cabinet.incoming.views')}</th>
                                            <th>{t('cabinet.incoming.when')}</th>
                                            <th>{t('cabinet.incoming.city')}</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {viewers.map((v) => (
                                            <tr key={v.id}>
                                                <td data-label={t('cabinet.incoming.company')}>
                                                    <CompanyCell row={v} seesNames={sees_names} />
                                                </td>
                                                <td data-label={t('cabinet.incoming.what_viewed')}>
                                                    <span className="t-sm">{v.looked || '—'}</span>
                                                </td>
                                                <td data-label={t('cabinet.incoming.views')}>
                                                    {tChoice('cabinet.incoming.views_count', v.views)}
                                                </td>
                                                <td data-label={t('cabinet.incoming.when')}>{v.when}</td>
                                                <td data-label={t('cabinet.incoming.city')}>{v.city}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                        </Section>
                    )}

                    {/* Ограничение объясняется прямо: непонятно скрытое название
                        раздражает, понятное — становится доводом за тариф */}
                    {!sees_names && (
                        <div className="card mt-24" style={{ background: 'var(--primary-50)', borderColor: 'var(--primary-100)' }}>
                            <div className="row-between wrap" style={{ gap: 16 }}>
                                <div style={{ flex: 1, minWidth: 260 }}>
                                    <b>{t('cabinet.incoming.names_locked')}</b>
                                    <p className="t-sm muted mt-8">
                                        {t('cabinet.incoming.names_locked_text', { plan: plan?.name ?? '' })}
                                    </p>
                                </div>
                                <Link href={routes.pricing} className="btn btn-primary">
                            {t('cabinet.incoming.compare_plans')}
                                </Link>
                            </div>
                        </div>
                    )}
                </>
            )}
        </CabinetLayout>
    );
}
