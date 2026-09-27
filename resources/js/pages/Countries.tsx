import { ArrowRight, Globe2, Star } from 'lucide-react';
import { VerificationBadge } from '@/components/VerificationBadge';
import { Link } from '@/components/ui/Link';
import { PublicLayout } from '@/layouts/PublicLayout';
import { flag } from '@/lib/flag';
import { t, tChoice } from '@/lib/i18n';
import { routes } from '@/routes';

interface CompanyRow {
    slug: string;
    name: string;
    type_label: string | null;
    city: string | null;
    verification_level: number;
    rating: number;
    listings_count: number;
    initials: string;
    logo: string | null;
}

interface CountryRow {
    code: string;
    name: string;
    companies: number;
    /** Верхушка компаний страны; остальные — по ссылке в каталог */
    items: CompanyRow[];
}

/**
 * Страны-участники площадки.
 *
 * Сверху — плашки стран для быстрого перехода, ниже под каждой
 * страной её компании и ссылка в каталог с фильтром по стране:
 * страница-справочник без действия — тупик, а не витрина.
 *
 * В шапке сайта страницы нет: сюда ведут счётчик «стран региона»
 * на главной и ссылка в подвале.
 */
export default function Countries({ countries, planned }: { countries: CountryRow[]; planned: CountryRow[] }) {
    return (
        <PublicLayout title={t('countries.meta_title')} description={t('countries.meta_description')}>
            <div className="container" style={{ paddingBlock: '32px 96px' }}>
                <div className="section-head-left" style={{ marginBottom: 24 }}>
                    <span className="eyebrow">{t('countries.eyebrow')}</span>
                    <h1 className="t-section">{t('countries.h1')}</h1>
                    <p className="t-lead">{t('countries.lead')}</p>
                </div>

                {countries.length === 0 ? (
                    <div className="card empty">
                        <div className="empty-icon">
                            <Globe2 aria-hidden className="size-7" />
                        </div>
                        <p className="t-h4">{t('countries.empty')}</p>
                    </div>
                ) : (
                    <>
                        {/* Быстрый переход к стране: плашки со счётчиками,
                            как на главной, ведут к её разделу ниже */}
                        <div className="country-grid" data-reveal-stagger>
                            {countries.map((c) => (
                                <a key={c.code} href={`#country-${c.code}`} className="country-card">
                                    <span className="country-flag" aria-hidden>
                                        {flag(c.code) || <Globe2 className="size-8" />}
                                    </span>
                                    <span style={{ minWidth: 0 }}>
                                        <span className="country-name" style={{ display: 'block' }}>
                                            {c.name}
                                        </span>
                                        <span className="country-count" style={{ display: 'block' }}>
                                            {tChoice('countries.companies', c.companies)}
                                        </span>
                                    </span>
                                </a>
                            ))}
                        </div>

                        {/* Под каждой страной — её компании */}
                        {countries.map((c) => (
                            <section key={c.code} id={`country-${c.code}`} className="country-section">
                                <div className="section-bar">
                                    <h2 className="country-section-title">
                                        <span aria-hidden>{flag(c.code) || <Globe2 className="size-6" />}</span>
                                        {c.name}
                                        <span className="country-count">
                                            {tChoice('countries.companies', c.companies)}
                                        </span>
                                    </h2>
                                    <Link href={`${routes.companies}?country=${c.code}`} className="section-bar-link">
                                        {t('countries.all_companies')} <ArrowRight aria-hidden className="go-arrow size-4" />
                                    </Link>
                                </div>
                                <div className="supplier-grid">
                                    {c.items.map((s) => (
                                        <Link key={s.slug} href={routes.company(s.slug)} className="supplier-card">
                                            <span className="supplier-head">
                                                <span className="listing-logo logo-48">
                                                    {s.logo ? <img src={s.logo} alt="" /> : s.initials}
                                                </span>
                                                <VerificationBadge level={s.verification_level} />
                                            </span>
                                            <span className="supplier-name">{s.name}</span>
                                            <span className="supplier-meta">
                                                {[s.type_label, s.city].filter(Boolean).join(' · ')}
                                            </span>
                                            <span className="supplier-facts">
                                                <span className="listing-rating">
                                                    <Star aria-hidden className="size-3.5" /> <b>{s.rating.toFixed(1)}</b>
                                                </span>
                                                <span>{tChoice('home.suppliers_listings', s.listings_count)}</span>
                                            </span>
                                        </Link>
                                    ))}
                                </div>
                            </section>
                        ))}
                    </>
                )}

                {/* Направления без компаний — отдельно и честно: это план,
                    а не факт. Ссылки нет — вести в пустой каталог незачем */}
                {planned.length > 0 && (
                    <>
                        <h2 className="t-h3" style={{ margin: '40px 0 16px' }}>{t('countries.planned_title')}</h2>
                        <p className="t-sm muted" style={{ marginBottom: 20 }}>{t('countries.planned_lead')}</p>
                        <div className="country-grid">
                            {planned.map((c) => (
                                <div key={c.code} className="country-card" style={{ opacity: 0.65 }}>
                                    <span className="country-flag" aria-hidden>
                                        {flag(c.code) || <Globe2 className="size-8" />}
                                    </span>
                                    <span style={{ minWidth: 0 }}>
                                        <span className="country-name" style={{ display: 'block' }}>
                                            {c.name}
                                        </span>
                                        <span className="country-count" style={{ display: 'block' }}>
                                            {t('countries.planned_badge')}
                                        </span>
                                    </span>
                                </div>
                            ))}
                        </div>
                    </>
                )}
            </div>
        </PublicLayout>
    );
}
