import { ArrowRight, Star } from 'lucide-react';
import { Link } from '@/components/ui/Link';
import { VerificationBadge } from '@/components/VerificationBadge';
import { PublicLayout } from '@/layouts/PublicLayout';
import { formatDecimal, t, tChoice } from '@/lib/i18n';
import { TIER_LOOK, type PartnerTierSlug } from '@/lib/partnerTiers';
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

/**
 * Страница одного вида партнёров: генеральные, партнёры или
 * мультипартнёры. Сверху — кто это такие, ниже — сами компании,
 * внизу — переход к двум другим видам.
 */
export default function PartnersTier({
    tier,
    partners,
    others,
}: {
    tier: PartnerTierSlug;
    partners: PartnerRow[];
    others: PartnerTierSlug[];
}) {
    const [Icon, tone] = TIER_LOOK[tier];
    const title = t(`partners.tiers.${tier}.title`);

    return (
        <PublicLayout title={title} description={t(`partners.tiers.${tier}.text`)}>
            <div className="container" style={{ paddingBottom: 96 }}>
                <nav aria-label={t('companies_page.crumbs')} style={{ padding: '20px 0 4px' }}>
                    <ol className="row t-sm muted" style={{ gap: 8, flexWrap: 'wrap' }}>
                        <li>
                            <Link href={routes.home}>{t('companies_page.home')}</Link>
                        </li>
                        <li aria-hidden="true">/</li>
                        <li>
                            <Link href={routes.partners}>{t('partners.title')}</Link>
                        </li>
                        <li aria-hidden="true">/</li>
                        <li aria-current="page" style={{ color: 'var(--text)' }}>
                            {title}
                        </li>
                    </ol>
                </nav>

                <div className="partner-tier-hero">
                    <span className={`stat-ico ${tone}`}>
                        <Icon aria-hidden className="size-6" />
                    </span>
                    <div style={{ minWidth: 0 }}>
                        <span className="eyebrow">{t('partners.eyebrow')}</span>
                        <h1 className="t-section">{title}</h1>
                        <p className="t-lead">{t(`partners.tiers.${tier}.text`)}</p>
                        <p className="t-sm muted mt-8">{tChoice('partners.count', partners.length)}</p>
                    </div>
                </div>

                {partners.length === 0 ? (
                    <div className="card empty">
                        <div className="empty-icon">
                            <Icon aria-hidden className="size-7" />
                        </div>
                        <p className="t-h4">{t(`partners.tiers.${tier}.empty`)}</p>
                    </div>
                ) : (
                    <div className="supplier-grid" data-reveal-stagger>
                        {partners.map((p) => (
                            <Link key={p.slug} href={routes.company(p.slug)} className="supplier-card">
                                <span className="supplier-head">
                                    <span className="listing-logo logo-48">
                                        {p.logo ? <img src={p.logo} alt="" /> : p.initials}
                                    </span>
                                    <VerificationBadge level={p.verification_level} />
                                </span>
                                <span className="supplier-name">{p.name}</span>
                                <span className="supplier-meta">
                                    {[p.type_label, p.city ?? p.country].filter(Boolean).join(' · ')}
                                </span>
                                <span className="supplier-facts">
                                    <span className="listing-rating">
                                        <Star aria-hidden className="size-3.5" /> <b>{formatDecimal(p.rating)}</b>
                                    </span>
                                    <span>{tChoice('home.suppliers_listings', p.listings_count)}</span>
                                </span>
                            </Link>
                        ))}
                    </div>
                )}

                {/* Соседние виды партнёрства — чтобы не возвращаться назад */}
                <h2 className="t-h4" style={{ margin: '48px 0 16px' }}>{t('partners.other_tiers')}</h2>
                <div className="partners-stats">
                    {others.map((slug) => {
                        const [OtherIcon, otherTone] = TIER_LOOK[slug];

                        return (
                            <Link key={slug} href={routes.partnersTier(slug)} className="partner-stat partner-tier-mini">
                                <span className={`stat-ico ${otherTone}`}>
                                    <OtherIcon aria-hidden className="size-5" />
                                </span>
                                <span className="partner-tier-title" style={{ flex: 1 }}>
                                    {t(`partners.tiers.${slug}.title`)}
                                </span>
                                <ArrowRight aria-hidden className="size-4" />
                            </Link>
                        );
                    })}
                </div>
            </div>
        </PublicLayout>
    );
}
