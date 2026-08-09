import { router } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { CalendarDays, CheckCircle2, Clock, FileText, Handshake, Search, Shield, Star } from 'lucide-react';
import { useState, type FormEvent } from 'react';
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
    completed_deals_count: number;
    response_time_hours: number | null;
    created_at: string | null;
    initials: string;
}

interface Paginated<T> {
    data: T[];
    links: { url: string | null; label: string; active: boolean }[];
    total: number;
}

function VerificationBadge({ level }: { level: number }) {
    if (level >= 3)
        return (
            <span className="badge badge-gold" title="Проверена расширенно">
                <Shield aria-hidden className="size-3.5" /> Проверена+
            </span>
        );
    if (level >= 2)
        return (
            <span className="badge badge-verified" title="Проверена модерацией">
                <CheckCircle2 aria-hidden className="size-3.5" /> Проверена
            </span>
        );
    return (
        <span className="badge badge-neutral" title="Документы не подтверждены">
            Не проверена
        </span>
    );
}

export default function CompaniesIndex({
    companies,
    filters,
    types,
    stats,
}: {
    companies: Paginated<CompanyRow>;
    filters: { q?: string; type?: string; verified?: boolean };
    /** Справочник типов компаний — редактируется в админке */
    types: Record<string, string>;
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
            title="Компании"
            description="Каталог компаний Узбекистана и Центральной Азии: производители, импортёры, дистрибьюторы. Фильтр по типу, городу и уровню проверки."
        >
            <div className="container">
                <nav aria-label="Хлебные крошки" style={{ padding: '20px 0 4px' }}>
                    <ol className="row t-sm muted" style={{ gap: 8, flexWrap: 'wrap' }}>
                        <li>
                            <Link href={routes.home}>Главная</Link>
                        </li>
                        <li aria-hidden="true">/</li>
                        <li aria-current="page" style={{ color: 'var(--text)' }}>
                            Компании
                        </li>
                    </ol>
                </nav>

                <div style={{ padding: '8px 0 0' }}>
                    <h1 className="t-h1">Компании</h1>
                    <p className="t-lead mt-8">
                        {stats.total} компаний · {stats.verified} проверены модерацией
                    </p>
                </div>

                <div className="catalog">
                    <aside className="filters" aria-label="Фильтры компаний">
                        <div className="filter-group">
                            <div className="filter-title">Тип компании</div>
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
                                    Все типы
                                </label>
                            </div>
                        </div>

                        <div className="filter-group">
                            <div className="filter-title">Надёжность</div>
                            <label className="check">
                                <input
                                    type="checkbox"
                                    checked={Boolean(filters.verified)}
                                    onChange={(e) => toggle('verified', e.target.checked || undefined)}
                                />
                                Только проверенные
                            </label>
                        </div>
                    </aside>

                    <div>
                        <div className="toolbar">
                            <form onSubmit={search} style={{ position: 'relative', flex: 1, minWidth: 240 }} role="search">
                                <label htmlFor="q" className="sr-only">
                                    Поиск компании
                                </label>
                                <input
                                    id="q"
                                    className="input"
                                    type="search"
                                    placeholder="Название компании или ИНН"
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
                                <h2 className="t-h3">По вашему запросу ничего нет</h2>
                                <p>Попробуйте убрать фильтр «Только проверенные» или изменить запрос.</p>
                                <button className="btn btn-primary" onClick={() => router.get(routes.companies)}>
                                    Сбросить фильтры
                                </button>
                            </div>
                        ) : (
                            <div className="grid grid-2">
                                {companies.data.map((c) => (
                                    <article key={c.slug} className="co-card">
                                        <div className="co-card-head">
                                            <span className="listing-logo logo-48">{c.initials}</span>
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
                                                <FileText aria-hidden className="size-4" /> ИНН <b>{c.tin ?? 'не указан'}</b>
                                            </span>
                                            <span className="co-fact">
                                                <CalendarDays aria-hidden className="size-4" /> с <b>{c.created_at}</b>
                                            </span>
                                            <span className="co-fact">
                                                <Clock aria-hidden className="size-4" /> отвечает за{' '}
                                                <b>{c.response_time_hours ? `${c.response_time_hours} ч` : '—'}</b>
                                            </span>
                                            <span className="co-fact">
                                                <Handshake aria-hidden className="size-4" /> сделок <b>{c.completed_deals_count}</b>
                                            </span>
                                        </div>

                                        <div
                                            className="row-between"
                                            style={{ paddingTop: 12, borderTop: '1px solid var(--border)' }}
                                        >
                                            <span className="t-sm muted">{c.reviews_count} отзывов</span>
                                            <Link href={routes.company(c.slug)} className="btn btn-outline btn-sm">
                                                Открыть визитку
                                            </Link>
                                        </div>
                                    </article>
                                ))}
                            </div>
                        )}

                        {companies.links.length > 3 && (
                            <nav className="row mt-32" style={{ justifyContent: 'center', gap: 6, flexWrap: 'wrap' }} aria-label="Страницы">
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
