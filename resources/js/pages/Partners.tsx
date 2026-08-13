import { ArrowRight, ShieldCheck, Star, Users } from 'lucide-react';
import { Link } from '@/components/ui/Link';
import { VerificationBadge } from '@/components/VerificationBadge';
import { formatNumber } from '@/components/cabinet';
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
    completed_deals_count: number;
    initials: string;
    logo: string | null;
}

/**
 * Партнёры площадки — витрина проверенных компаний.
 *
 * Показывает верхушку по проверке и рейтингу: страница продаёт
 * доверие, а не полный справочник. Полный каталог — по ссылке ниже.
 */
export default function Partners({
    partners,
    stats,
}: {
    partners: PartnerRow[];
    stats: { total: number; verified: number; deals: number };
}) {
    const cells: [typeof Users, string, number, string][] = [
        [Users, 'stat-ico-blue', stats.total, t('partners.stat_total')],
        [ShieldCheck, 'stat-ico-sky', stats.verified, t('partners.stat_verified')],
        [Star, 'stat-ico-violet', stats.deals, t('partners.stat_deals')],
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
                    {partners.length === 0 ? (
                        <div className="card empty">
                            <div className="empty-icon">
                                <ShieldCheck aria-hidden className="size-7" />
                            </div>
                            <p className="t-h4">{t('partners.empty')}</p>
                        </div>
                    ) : (
                        <>
                            <div className="supplier-grid" data-reveal-stagger>
                                {partners.map((p) => (
                                    <Link key={p.slug} href={routes.company(p.slug)} className="supplier-card">
                                        <span className="supplier-head">
                                            <span className="listing-logo logo-48">{p.initials}</span>
                                            <VerificationBadge level={p.verification_level} />
                                        </span>
                                        <span className="supplier-name">{p.name}</span>
                                        <span className="supplier-meta">
                                            {[p.type_label, p.city ?? p.country].filter(Boolean).join(' · ')}
                                        </span>
                                        <span className="supplier-facts">
                                            <span className="listing-rating">
                                                <Star aria-hidden className="size-3.5" /> <b>{p.rating.toFixed(1)}</b>
                                            </span>
                                            <span>{tChoice('home.suppliers_deals', p.completed_deals_count)}</span>
                                        </span>
                                    </Link>
                                ))}
                            </div>

                            <div className="row" style={{ justifyContent: 'center', marginTop: 36 }}>
                                <Link href={routes.companies} className="btn btn-secondary btn-lg">
                                    {t('partners.all_companies')} <ArrowRight aria-hidden className="size-4" />
                                </Link>
                            </div>
                        </>
                    )}
                </div>
            </section>
        </PublicLayout>
    );
}
