import { ArrowRight } from 'lucide-react';
import { CountUp } from '@/components/CountUp';
import { Link } from '@/components/ui/Link';
import { PublicLayout } from '@/layouts/PublicLayout';
import { t } from '@/lib/i18n';
import { TIER_LOOK, type PartnerTierSlug } from '@/lib/partnerTiers';
import { routes } from '@/routes';

/**
 * Партнёры площадки: три вида партнёрства.
 *
 * Страница — вход в раздел: у каждого вида ячейка со счётчиком
 * и коротким описанием, кто это такие, а сами списки живут на
 * отдельных страницах (/partners/general, /regular, /multi).
 * Состав назначает администратор действием «Партнёрство» в админке.
 */
export default function Partners({ tiers }: { tiers: { slug: PartnerTierSlug; count: number }[] }) {
    return (
        <PublicLayout title={t('partners.meta_title')} description={t('partners.meta_description')}>
            <div className="container" style={{ paddingBottom: 96 }}>
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

                {/* Три вида партнёрства: кто это такие, сколько их и ссылка
                    на отдельную страницу со списком */}
                <div className="partners-stats partner-tiers" data-reveal-stagger>
                    {tiers.map(({ slug, count }) => {
                        const [Icon, tone] = TIER_LOOK[slug];

                        return (
                            <Link key={slug} href={routes.partnersTier(slug)} className="partner-stat partner-tier">
                                <span className="partner-tier-head">
                                    <span className={`stat-ico ${tone}`}>
                                        <Icon aria-hidden className="size-5" />
                                    </span>
                                    <span style={{ minWidth: 0 }}>
                                        <span className="stat-cell-num" style={{ display: 'block' }}>
                                            <CountUp value={count} />
                                        </span>
                                        <span className="partner-tier-title">{t(`partners.tiers.${slug}.title`)}</span>
                                    </span>
                                </span>
                                <span className="partner-tier-text">{t(`partners.tiers.${slug}.text`)}</span>
                                <span className="partner-tier-go">
                                    {t('partners.open')} <ArrowRight aria-hidden className="size-4" />
                                </span>
                            </Link>
                        );
                    })}
                </div>
            </div>
        </PublicLayout>
    );
}
