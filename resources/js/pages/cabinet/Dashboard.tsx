import { usePage } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import {
    Building2,
    Clock,
    CreditCard,
    Eye,
    FileText,
    Plus,
    Rocket,
    Star,
    TriangleAlert,
} from 'lucide-react';
import type { ComponentType } from 'react';
import { LimitBar, Metric, Panel, type MetricData } from '@/components/cabinet';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { cn } from '@/lib/cn';
import { routes } from '@/routes';
import type { SharedProps } from '@/types';
import { t, tChoice } from '@/lib/i18n';

interface Props {
    company: { name: string; slug: string; completeness: number; missing: string[] } | null;
    metrics: Record<'impressions' | 'views' | 'unlocks' | 'conversion', MetricData> | null;
    series: Record<'impressions' | 'views' | 'unlocks', number[]> | null;
    events: { id: number; type: string; tone: string; message: string; url: string | null; ago: string }[];
    limits: {
        listings: { used: number; total: number | null };
        contacts: { used: number; total: number | null };
        promo: { used: number; total: number };
        resets_at: string | null;
    } | null;
    plan: { name: string; until: string | null } | null;
    expiring: number;
    drafts: number;
}

const EVENT_ICONS: Record<string, ComponentType<{ className?: string; 'aria-hidden'?: boolean }>> = {
    unlock: Eye,
    review: Star,
    promotion: Rocket,
    expiry: Clock,
    moderation: FileText,
    payment: CreditCard,
};

const TONE_CLASS: Record<string, string> = {
    success: 'ico-box-success',
    warning: 'ico-box-warning',
    danger: 'ico-box-danger',
    info: '',
};

export default function Dashboard({ company, metrics, series, events, limits, plan, expiring, drafts }: Props) {
    const { auth } = usePage<SharedProps>().props;
    const verified = Boolean(auth?.user?.email_verified);
    const firstName = auth?.user?.name?.split(' ')[0] ?? '';

    if (!company) {
        return (
            <CabinetLayout title={t('cabinet.dashboard.title')} heading={t('cabinet.dashboard.hello', { name: firstName }).trim()}>
                <div className="card empty">
                    <div className="empty-icon">
                        <Building2 aria-hidden className="size-7" />
                    </div>
                    <p className="t-h4">{t('cabinet.dashboard.no_company_title')}</p>
                    <p className="t-sm muted mt-8" style={{ maxWidth: 460, margin: '8px auto 0' }}>
                        {t('cabinet.dashboard.no_company_text')}
                    </p>
                    <Link href={routes.cabinetCompany} className="btn btn-primary mt-24">
                        {t('cabinet.dashboard.no_company_action')}
                    </Link>
                </div>
            </CabinetLayout>
        );
    }

    const incomplete = company.completeness < 100;

    return (
        <CabinetLayout
            title={t('cabinet.dashboard.title')}
            heading={t('cabinet.dashboard.hello', { name: firstName }).trim()}
            subheading={
                <>
                    {company.name}
                    {plan && ` · ${t('cabinet.dashboard.plan', { name: plan.name })}`}
                    {plan?.until && ` ${t('cabinet.dashboard.plan_until', { date: plan.until })}`}
                </>
            }
            actions={
                <Link
                    href={routes.listingCreate}
                    className={cn('btn btn-primary', !verified && 'is-disabled')}
                    aria-disabled={!verified || undefined}
                    title={verified ? undefined : t('cabinet.dashboard.verify_first')}
                >
                    <Plus aria-hidden className="size-4" /> {t('cabinet.dashboard.new_listing')}
                </Link>
            }
        >
            {/* Незаполненный профиль вредит конверсии сильнее, чем кажется:
                покупатель не звонит компании без адреса и документов */}
            {incomplete && (
                <div className="card" style={{ background: 'var(--warning-bg)', borderColor: 'rgba(245,158,11,.3)', marginBottom: 24 }}>
                    <div className="row-between wrap" style={{ gap: 16 }}>
                        <div style={{ flex: 1, minWidth: 260 }}>
                            <b>{t('cabinet.dashboard.completeness', { percent: company.completeness })}</b>
                            <div className="progress mt-8" style={{ maxWidth: 340 }}>
                                <div className="progress-fill" style={{ width: `${company.completeness}%`, background: 'var(--warning)' }} />
                            </div>
                            {company.missing.length > 0 && (
                                <p className="t-sm mt-8" style={{ color: '#78350F' }}>
                                    {t('cabinet.dashboard.missing', { fields: company.missing.join(', ') })}
                                </p>
                            )}
                        </div>
                        <Link href={routes.cabinetCompany} className="btn btn-secondary">
                            {t('cabinet.dashboard.complete')}
                        </Link>
                    </div>
                </div>
            )}

            {metrics && series && (
                <div className="grid grid-4 grid-tight">
                    <Metric label={t('cabinet.dashboard.impressions')} data={metrics.impressions} series={series.impressions} />
                    <Metric label={t('cabinet.dashboard.views')} data={metrics.views} series={series.views} />
                    <Metric label={t('cabinet.dashboard.unlocks')} data={metrics.unlocks} series={series.unlocks} />
                    <Metric label={t('cabinet.dashboard.conversion')} data={metrics.conversion} />
                </div>
            )}

            <div className="grid grid-split mt-24" style={{ ['--split' as string]: '1.4fr 1fr' }}>
                <Panel
                    title={t('cabinet.dashboard.events')}
                    action={
                        <Link href={routes.cabinetIncoming} className="t-sm">
                            {t('cabinet.dashboard.events_all')}
                        </Link>
                    }
                >
                    {events.length === 0 ? (
                        <p className="muted t-sm">
                            {t('cabinet.dashboard.events_empty')}
                        </p>
                    ) : (
                        <ul className="stack-16">
                            {events.map((e) => {
                                const Icon = EVENT_ICONS[e.type] ?? Eye;
                                return (
                                    <li key={e.id} className="row" style={{ gap: 12, alignItems: 'flex-start' }}>
                                        <span className={cn('ico-box ico-box-sm', TONE_CLASS[e.tone])}>
                                            <Icon aria-hidden className="size-4" />
                                        </span>
                                        <span className="t-sm" style={{ flex: 1 }}>
                                            {e.message}
                                            <br />
                                            <span className="muted t-caption">{e.ago}</span>
                                        </span>
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </Panel>

                {limits && plan && (
                    <Panel title={t('cabinet.dashboard.limits', { name: plan.name })}>
                        <div className="stack-16">
                            <LimitBar label={t('cabinet.dashboard.limit_listings')} used={limits.listings.used} total={limits.listings.total} />
                            <LimitBar
                                label={t('cabinet.dashboard.limit_contacts')}
                                used={limits.contacts.used}
                                total={limits.contacts.total}
                            />
                            <LimitBar label={t('cabinet.dashboard.limit_promo')} used={limits.promo.used} total={limits.promo.total} />
                        </div>
                        {limits.resets_at && <p className="t-sm muted mt-16">{t('cabinet.dashboard.limit_resets', { date: limits.resets_at })}</p>}
                        <Link href={routes.cabinetBilling} className="btn btn-secondary btn-block mt-16">
                            {t('cabinet.dashboard.manage_plan')}
                        </Link>
                    </Panel>
                )}
            </div>

            {(expiring > 0 || drafts > 0) && (
                <div className="grid grid-2 mt-24">
                    {expiring > 0 && (
                        <div className="alert alert-warning">
                            <TriangleAlert aria-hidden className="size-5" />
                            <div>
                                <b>{tChoice('cabinet.dashboard.expiring', expiring)}</b>{' '}
                                {t('cabinet.dashboard.expiring_text')}{' '}
                                <Link href={routes.cabinetListings}>{t('cabinet.dashboard.check')}</Link>
                            </div>
                        </div>
                    )}
                    {drafts > 0 && (
                        <div className="alert alert-info">
                            <FileText aria-hidden className="size-5" />
                            <div>
                                {t('cabinet.dashboard.drafts', { count: drafts })}{' '}
                                <Link href={routes.cabinetListings}>{t('cabinet.dashboard.open')}</Link>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </CabinetLayout>
    );
}
