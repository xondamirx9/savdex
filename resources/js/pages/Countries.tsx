import { Globe2 } from 'lucide-react';
import { Link } from '@/components/ui/Link';
import { PublicLayout } from '@/layouts/PublicLayout';
import { flag } from '@/lib/flag';
import { t, tChoice } from '@/lib/i18n';
import { routes } from '@/routes';

interface CountryRow {
    code: string;
    name: string;
    companies: number;
}

/**
 * Страны-участники площадки.
 *
 * Каждая карточка ведёт в каталог компаний с фильтром по стране:
 * страница-справочник без действия — тупик, а не витрина.
 */
export default function Countries({ countries }: { countries: CountryRow[] }) {
    return (
        <PublicLayout title={t('countries.meta_title')} description={t('countries.meta_description')}>
            <div className="container" style={{ padding: '32px 0 96px' }}>
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
                    <div className="country-grid" data-reveal-stagger>
                        {countries.map((c) => (
                            <Link
                                key={c.code}
                                href={`${routes.companies}?country=${c.code}`}
                                className="country-card"
                            >
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
                            </Link>
                        ))}
                    </div>
                )}
            </div>
        </PublicLayout>
    );
}
