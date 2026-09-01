import { router } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { CalendarDays, FileText, Globe, Handshake, Search, Star } from 'lucide-react';
import { useState, type FormEvent } from 'react';
import { VerificationBadge } from '@/components/VerificationBadge';
import { t, tChoice } from '@/lib/i18n';
import { PublicLayout } from '@/layouts/PublicLayout';
import { routes } from '@/routes';

interface CompanyRow {
    slug: string;
    name: string;
    tin: string | null;
    type: string | null;
    type_label: string | null;
    city: string | null;
    verification_level: number;
    rating: number;
    reviews_count: number;
    trust: number;
    created_at: string | null;
    initials: string;
    logo: string | null;
    website: string | null;
}

/**
 * Возраст регистрации: значения понятны в адресной строке (?age=lt1).
 * Функция, а не константа модуля: подписи берутся из словаря,
 * а он приходит с сервером после загрузки файла.
 */
const ageOptions = (): [string, string][] => [
    ['lt1', t('companies_page.age_lt1')],
    ['1to5', t('companies_page.age_1to5')],
    ['gt5', t('companies_page.age_gt5')],
];

interface Paginated<T> {
    data: T[];
    links: { url: string | null; label: string; active: boolean }[];
    total: number;
}

export default function CompaniesIndex({
    companies,
    filters,
    types,
    countries,
    stats,
}: {
    companies: Paginated<CompanyRow>;
    filters: { q?: string; type?: string; verified?: boolean; country?: string; age?: string };
    /** Справочник типов компаний — редактируется в админке */
    types: Record<string, string>;
    countries: { code: string; name: string }[];
    stats: { total: number; verified: number };
}) {
    const [q, setQ] = useState(filters.q ?? '');

    function search(e: FormEvent) {
        e.preventDefault();
        // preserveState держит открытые фильтры, replace не засоряет историю
        router.get(routes.companies, { ...filters, q }, { preserveState: true, replace: true });
    }

    function toggle(key: string, value: string | boolean | undefined) {
        const next = { ...filters, [key]: value };
        if (!value) delete next[key as keyof typeof next];
        router.get(routes.companies, next, { preserveState: true, replace: true });
    }

    return (
        <PublicLayout
            title={t('companies_page.title')}
            description={t('companies_page.meta_description')}
        >
            <div className="container">
                <nav aria-label={t('companies_page.crumbs')} style={{ padding: '20px 0 4px' }}>
                    <ol className="row t-sm muted" style={{ gap: 8, flexWrap: 'wrap' }}>
                        <li>
                            <Link href={routes.home}>{t('companies_page.home')}</Link>
                        </li>
                        <li aria-hidden="true">/</li>
                        <li aria-current="page" style={{ color: 'var(--text)' }}>
                            {t('companies_page.title')}
                        </li>
                    </ol>
                </nav>

                <div style={{ padding: '8px 0 0' }}>
                    <h1 className="t-h1">{t('companies_page.title')}</h1>
                    <p className="t-lead mt-8">
                        {t('companies_page.stats', { total: stats.total, verified: stats.verified })}
                    </p>
                </div>

                <div className="catalog">
                    <aside className="filters" aria-label={t('companies_page.filters_aria')}>
                        <div className="filter-group">
                            <div className="filter-title">{t('companies_page.type_title')}</div>
                            <div className="filter-list">
                                {Object.entries(types).map(([value, label]) => (
                                    <label key={value} className="check">
                                        <input
                                            type="radio"
                                            name="type"
                                            checked={filters.type === value}
                                            onChange={() => toggle('type', value)}
                                        />
                                        {label}
                                    </label>
                                ))}
                                <label className="check">
                                    <input type="radio" name="type" checked={!filters.type} onChange={() => toggle('type', undefined)} />
                                    {t('companies_page.type_all')}
                                </label>
                            </div>
                        </div>

                        <div className="filter-group">
                            <div className="filter-title">{t('companies_page.country_title')}</div>
                            <div className="filter-list">
                                {countries.map((c) => (
                                    <label key={c.code} className="check">
                                        <input
                                            type="radio"
                                            name="country"
                                            checked={filters.country === c.code}
                                            onChange={() => toggle('country', c.code)}
                                        />
                                        {c.name}
                                    </label>
                                ))}
                                <label className="check">
                                    <input
                                        type="radio"
                                        name="country"
                                        checked={!filters.country}
                                        onChange={() => toggle('country', undefined)}
                                    />
                                    {t('companies_page.country_all')}
                                </label>
                            </div>
                        </div>

                        <div className="filter-group">
                            <div className="filter-title">{t('companies_page.age_title')}</div>
                            <div className="filter-list">
                                {ageOptions().map(([value, label]) => (
                                    <label key={value} className="check">
                                        <input
                                            type="radio"
                                            name="age"
                                            checked={filters.age === value}
                                            onChange={() => toggle('age', value)}
                                        />
                                        {label}
                                    </label>
                                ))}
                                <label className="check">
                                    <input type="radio" name="age" checked={!filters.age} onChange={() => toggle('age', undefined)} />
                                    {t('companies_page.age_any')}
                                </label>
                            </div>
                        </div>

                        <div className="filter-group">
                            <div className="filter-title">{t('companies_page.trust_title')}</div>
                            <label className="check">
                                <input
                                    type="checkbox"
                                    checked={Boolean(filters.verified)}
                                    onChange={(e) => toggle('verified', e.target.checked || undefined)}
                                />
                                {t('companies_page.trust_only')}
                            </label>
                        </div>
                    </aside>

                    <div>
                        <div className="toolbar">
                            <form onSubmit={search} style={{ position: 'relative', flex: 1, minWidth: 240 }} role="search">
                                <label htmlFor="q" className="sr-only">
                                    {t('companies_page.search_label')}
                                </label>
                                <input
                                    id="q"
                                    className="input"
                                    type="search"
                                    placeholder={t('companies_page.search_placeholder')}
                                    style={{ paddingLeft: 42 }}
                                    value={q}
                                    onChange={(e) => setQ(e.target.value)}
                                />
                                <Search
                                    aria-hidden
                                    className="text-muted pointer-events-none absolute top-1/2 left-3.5 size-5 -translate-y-1/2"
                                />
                            </form>
                        </div>

                        {companies.data.length === 0 ? (
                            <div className="empty">
                                <div className="empty-icon">
                                    <Search aria-hidden className="size-8" />
                                </div>
                                <h2 className="t-h3">{t('companies_page.empty_title')}</h2>
                                <p>{t('companies_page.empty_text')}</p>
                                <button className="btn btn-primary" onClick={() => router.get(routes.companies)}>
                                    {t('companies_page.empty_reset')}
                                </button>
                            </div>
                        ) : (
                            <div className="grid grid-2">
                                {companies.data.map((c) => (
                                    <article key={c.slug} className="co-card">
                                        <div className="co-card-head">
                                            <span className="listing-logo logo-48">
                                                {c.logo ? <img src={c.logo} alt="" /> : c.initials}
                                            </span>
                                            <div style={{ flex: 1, minWidth: 0 }}>
                                                <div className="row wrap" style={{ gap: 8, marginBottom: 4 }}>
                                                    <Link href={routes.company(c.slug)} className="t-h4" style={{ color: 'var(--text)' }}>
                                                        {c.name}
                                                    </Link>
                                                    <VerificationBadge level={c.verification_level} />
                                                </div>
                                                <p className="t-sm muted">
                                                    {[c.type_label, c.city].filter(Boolean).join(' · ')}
                                                </p>
                                            </div>
                                            <div className="listing-rating" style={{ margin: 0 }}>
                                                <Star aria-hidden className="size-3.5" /> <b>{c.rating.toFixed(1)}</b>
                                            </div>
                                        </div>

                                        <div className="co-facts">
                                            <span className="co-fact">
                                                <FileText aria-hidden className="size-4" /> {t('companies_page.tin')} <b>{c.tin ?? t('companies_page.tin_none')}</b>
                                            </span>
                                            <span className="co-fact">
                                                <CalendarDays aria-hidden className="size-4" /> <b>{t('companies_page.since', { date: c.created_at ?? '—' })}</b>
                                            </span>
                                            <span className="co-fact">
                                                <Handshake aria-hidden className="size-4" /> {t('companies_page.trust')} <b>{c.trust}%</b>
                                            </span>
                                        </div>

                                        <div
                                            className="row-between"
                                            style={{ paddingTop: 12, borderTop: '1px solid var(--border)' }}
                                        >
                                            <span className="t-sm muted">{tChoice('companies_page.reviews', c.reviews_count)}</span>
                                            <span className="row" style={{ gap: 8 }}>
                                                {c.website && (
                                                    <a
                                                        href={c.website}
                                                        target="_blank"
                                                        rel="noopener nofollow"
                                                        className="btn btn-ghost btn-sm"
                                                    >
                                                        <Globe aria-hidden className="size-4" /> {t('companies_page.website')}
                                                    </a>
                                                )}
                                                <Link href={routes.company(c.slug)} className="btn btn-outline btn-sm">
                                                    {t('companies_page.open_card')}
                                                </Link>
                                            </span>
                                        </div>
                                    </article>
                                ))}
                            </div>
                        )}

                        {companies.links.length > 3 && (
                            <nav className="row mt-32" style={{ justifyContent: 'center', gap: 6, flexWrap: 'wrap' }} aria-label={t('companies_page.pages')}>
                                {companies.links.map((l) =>
                                    l.url ? (
                                        <Link
                                            key={l.label}
                                            href={l.url}
                                            className={`btn btn-sm ${l.active ? 'btn-primary' : 'btn-secondary'}`}
                                            aria-current={l.active ? 'page' : undefined}
                                            dangerouslySetInnerHTML={{ __html: l.label }}
                                        />
                                    ) : (
                                        <span key={l.label} className="muted" style={{ padding: '0 6px' }}>
                                            …
                                        </span>
                                    ),
                                )}
                            </nav>
                        )}
                    </div>
                </div>
            </div>
        </PublicLayout>
    );
}
