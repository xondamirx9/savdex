import { ArrowRight, Boxes, Crown, Handshake, ShieldCheck, Star, Users } from 'lucide-react';
import { useState } from 'react';
import { Link } from '@/components/ui/Link';
import { VerificationBadge } from '@/components/VerificationBadge';
import { Tabs, formatNumber } from '@/components/cabinet';
import { PublicLayout } from '@/layouts/PublicLayout';
import { t, tChoice } from '@/lib/i18n';
import { routes } from '@/routes';

interface PartnerRow {
    slug: string;
    name: string;
    type_label: string | null;
    city: string | null;
    country: string | null;
    verification_level: number;
    rating: number;
    reviews_count: number;
    listings_count: number;
    initials: string;
    logo: string | null;
}

type Tier = 'general' | 'partners';

/**
 * Партнёры площадки: две вкладки — генеральные и обычные партнёры.
 *
 * Состав назначает администратор (действие «Партнёрство» в админке),
 * поэтому страница ничего не отбирает сама. Вкладка запоминается
 * в адресе (?tab=partners) — на неё можно дать ссылку.
 */
function initialTier(general: PartnerRow[]): Tier {
    if (typeof window !== 'undefined') {
        const tab = new URLSearchParams(window.location.search).get('tab');

        if (tab === 'general' || tab === 'partners') return tab;
    }

    // Генеральных ещё не назначили — сразу открываем тех, кто есть
    return general.length > 0 ? 'general' : 'partners';
}

function PartnerCard({ p }: { p: PartnerRow }) {
    return (
        <Link href={routes.company(p.slug)} className="supplier-card">
            <span className="supplier-head">
                <span className="listing-logo logo-48">{p.logo ? <img src={p.logo} alt="" /> : p.initials}</span>
                <VerificationBadge level={p.verification_level} />
            </span>
            <span className="supplier-name">{p.name}</span>
            <span className="supplier-meta">{[p.type_label, p.city ?? p.country].filter(Boolean).join(' · ')}</span>
            <span className="supplier-facts">
                <span className="listing-rating">
                    <Star aria-hidden className="size-3.5" /> <b>{p.rating.toFixed(1)}</b>
                </span>
                <span>{tChoice('home.suppliers_listings', p.listings_count)}</span>
            </span>
        </Link>
    );
}

export default function Partners({
    general,
    partners,
    stats,
}: {
    general: PartnerRow[];
    partners: PartnerRow[];
    stats: { total: number; verified: number; listings: number };
}) {
    const [tier, setTier] = useState<Tier>(() => initialTier(general));
    const rows = tier === 'general' ? general : partners;

    function choose(key: string) {
        const next = key === 'general' ? 'general' : 'partners';
        setTier(next);

        const url = new URL(window.location.href);
        url.searchParams.set('tab', next);
        window.history.replaceState(window.history.state, '', url);
    }

    const cells: [typeof Users, string, number, string][] = [
        [Users, 'stat-ico-blue', stats.total, t('partners.stat_total')],
        [ShieldCheck, 'stat-ico-sky', stats.verified, t('partners.stat_verified')],
        [Boxes, 'stat-ico-violet', stats.listings, t('partners.stat_listings')],
    ];

    return (
        <PublicLayout title={t('partners.meta_title')} description={t('partners.meta_description')}>
            <div className="container">
                <nav aria-label={t('companies_page.crumbs')} style={{ padding: '20px 0 4px' }}>
                    <ol className="row t-sm muted" style={{ gap: 8, flexWrap: 'wrap' }}>
                        <li>
                            <Link href={routes.home}>{t('companies_page.home')}</Link>
                        </li>
                        <li aria-hidden="true">/</li>
                        <li aria-current="page" style={{ color: 'var(--text)' }}>
                            {t('partners.title')}
                        </li>
                    </ol>
                </nav>

                <div className="section-head-left" style={{ padding: '8px 0 0', marginBottom: 28 }}>
                    <span className="eyebrow">{t('partners.eyebrow')}</span>
                    <h1 className="t-section">{t('partners.h1')}</h1>
                    <p className="t-lead">{t('partners.lead')}</p>
                </div>

                <div className="partners-stats" data-reveal-stagger>
                    {cells.map(([Icon, tone, value, label]) => (
                        <div key={label} className="partner-stat">
                            <span className={`stat-ico ${tone}`}>
                                <Icon aria-hidden className="size-5" />
                            </span>
                            <div style={{ minWidth: 0 }}>
                                <div className="stat-cell-num">{formatNumber(value)}</div>
                                <div className="stat-cell-label">{label}</div>
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            <section className="section--tight">
                <div className="container">
                    <Tabs
                        label={t('partners.tabs_label')}
                        active={tier}
                        onChange={choose}
                        items={[
                            { key: 'general', label: t('partners.tab_general'), count: general.length },
                            { key: 'partners', label: t('partners.tab_partners'), count: partners.length },
                        ]}
                    />
                    <p className="t-sm muted" style={{ margin: '-4px 0 20px' }}>
                        {tier === 'general' ? t('partners.general_lead') : t('partners.partners_lead')}
                    </p>

                    <div role="tabpanel">
                        {rows.length === 0 ? (
                            <div className="card empty">
                                <div className="empty-icon">
                                    {tier === 'general' ? (
                                        <Crown aria-hidden className="size-7" />
                                    ) : (
                                        <Handshake aria-hidden className="size-7" />
                                    )}
                                </div>
                                <p className="t-h4">
                                    {tier === 'general' ? t('partners.empty_general') : t('partners.empty_partners')}
                                </p>
                            </div>
                        ) : (
                            <div className="supplier-grid">
                                {rows.map((p) => (
                                    <PartnerCard key={p.slug} p={p} />
                                ))}
                            </div>
                        )}
                    </div>

                    <div className="row" style={{ justifyContent: 'center', marginTop: 36 }}>
                        <Link href={routes.companies} className="btn btn-secondary btn-lg">
                            {t('partners.all_companies')} <ArrowRight aria-hidden className="size-4" />
                        </Link>
                    </div>
                </div>
            </section>
        </PublicLayout>
    );
}
