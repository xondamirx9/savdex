import { ArrowRight, ChevronDown, Globe2, Star } from 'lucide-react';
import { useState } from 'react';
import { VerificationBadge } from '@/components/VerificationBadge';
import { Button } from '@/components/ui/Button';
import { Link } from '@/components/ui/Link';
import { PublicLayout } from '@/layouts/PublicLayout';
import { flag } from '@/lib/flag';
import { localize } from '@/lib/locale';
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
    /** Первые компании страны; остальные — по «Показать ещё» */
    items: CompanyRow[];
}

/**
 * Страны-участники площадки.
 *
 * Сверху — плашки стран для быстрого перехода, ниже под каждой
 * страной её компании: первые сразу, все остальные — одним
 * нажатием «Показать ещё».
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
                            <CountrySection key={c.code} country={c} />
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

/**
 * Раздел страны: её компании и кнопка «Показать ещё».
 *
 * Сервер отдаёт сразу только первые компании — всего их больше
 * тысячи, и страница со всеми карточками грузилась бы долго.
 * Нажатие подгружает всех оставшихся компаний страны разом.
 */
function CountrySection({ country: c }: { country: CountryRow }) {
    const [items, setItems] = useState(c.items);
    const [loading, setLoading] = useState(false);
    const [failed, setFailed] = useState(false);
    const hasMore = items.length < c.companies;

    const loadMore = async () => {
        setLoading(true);
        setFailed(false);

        try {
            const res = await fetch(localize(`${routes.countries}/${c.code}/companies?offset=${items.length}`), {
                headers: { Accept: 'application/json' },
            });

            if (!res.ok) throw new Error(String(res.status));

            const data: { items: CompanyRow[] } = await res.json();
            // Ключ — slug: при повторном нажатии дубли не появятся
            setItems((prev) => {
                const seen = new Set(prev.map((s) => s.slug));
                return [...prev, ...data.items.filter((s) => !seen.has(s.slug))];
            });
        } catch {
            setFailed(true);
        } finally {
            setLoading(false);
        }
    };

    return (
        <section id={`country-${c.code}`} className="country-section">
            <div className="section-bar">
                <h2 className="country-section-title">
                    <span aria-hidden>{flag(c.code) || <Globe2 className="size-6" />}</span>
                    {c.name}
                    <span className="country-count">{tChoice('countries.companies', c.companies)}</span>
                </h2>
                <Link href={`${routes.companies}?country=${c.code}`} className="section-bar-link">
                    {t('countries.all_companies')} <ArrowRight aria-hidden className="go-arrow size-4" />
                </Link>
            </div>
            <div className="supplier-grid">
                {items.map((s) => (
                    <Link key={s.slug} href={routes.company(s.slug)} className="supplier-card">
                        <span className="supplier-head">
                            <span className="listing-logo logo-48">
                                {s.logo ? <img src={s.logo} alt="" loading="lazy" /> : s.initials}
                            </span>
                            <VerificationBadge level={s.verification_level} />
                        </span>
                        <span className="supplier-name">{s.name}</span>
                        <span className="supplier-meta">{[s.type_label, s.city].filter(Boolean).join(' · ')}</span>
                        <span className="supplier-facts">
                            <span className="listing-rating">
                                <Star aria-hidden className="size-3.5" /> <b>{s.rating.toFixed(1)}</b>
                            </span>
                            <span>{tChoice('home.suppliers_listings', s.listings_count)}</span>
                        </span>
                    </Link>
                ))}
            </div>
            {hasMore && (
                <div className="country-more">
                    <Button variant="secondary" loading={loading} onClick={loadMore}>
                        {!loading && <ChevronDown aria-hidden className="size-4" />}
                        {t('countries.show_more')}
                        <span className="muted">({c.companies - items.length})</span>
                    </Button>
                    {failed && <p className="t-sm muted" role="alert">{t('countries.load_failed')}</p>}
                </div>
            )}
        </section>
    );
}
