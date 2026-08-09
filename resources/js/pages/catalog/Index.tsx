import { router } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { Package, Search, SlidersHorizontal, X } from 'lucide-react';
import { useState } from 'react';
import { ProductCard, type ProductRow } from '@/components/ProductCard';
import { PublicLayout } from '@/layouts/PublicLayout';
import { cn } from '@/lib/cn';
import { t, tChoice } from '@/lib/i18n';
import { routes } from '@/routes';

interface Props {
    listings: {
        data: ProductRow[];
        links: { url: string | null; label: string; active: boolean }[];
        current_page: number;
        last_page: number;
    };
    filters: {
        q: string;
        type: string;
        category: number | null;
        city: number | null;
        verified: boolean;
        with_price: boolean;
        sort: string;
    };
    sorts: Record<string, string>;
    categories: { id: number; name: string; children: { id: number; name: string }[] }[];
    cities: { id: number; name: string }[];
    total: number;
}

export default function CatalogIndex({ listings, filters, sorts, categories, cities, total }: Props) {
    const [q, setQ] = useState(filters.q);
    const [filtersOpen, setFiltersOpen] = useState(false);

    function apply(next: Partial<Props['filters']>) {
        router.get(
            routes.catalog,
            // Пустые значения выкидываются: адрес с «?type=&city=»
            // невозможно ни прочитать, ни переслать коллеге
            Object.fromEntries(
                Object.entries({ ...filters, ...next }).filter(([, v]) => v !== '' && v !== null && v !== false),
            ),
            { preserveState: true, preserveScroll: true, replace: true },
        );
    }

    const hasFilters =
        filters.type !== '' || filters.category !== null || filters.city !== null ||
        filters.verified || filters.with_price;

    return (
        <PublicLayout
            title={t('catalog.meta_title')}
            description={t('catalog.meta_description')}
        >
            <div className="container catalog">
                <aside className={cn('filters', filtersOpen && 'open')}>
                    <div className="filter-group">
                        <div className="filter-title">
                            {t('catalog.filters')}
                            {hasFilters && (
                                <button
                                    className="t-caption"
                                    onClick={() =>
                                        router.get(routes.catalog, filters.q ? { q: filters.q } : {})
                                    }
                                >
                                    {t('catalog.reset')}
                                </button>
                            )}
                        </div>

                        <div className="row wrap" style={{ gap: 6 }}>
                            {(
                                [
                                    ['', t('catalog.type_all')],
                                    ['supply', t('catalog.type_supply')],
                                    ['demand', t('catalog.type_demand')],
                                ] as const
                            ).map(([value, label]) => (
                                <button
                                    key={value || 'all'}
                                    className={cn('chip', filters.type === value && 'chip-active')}
                                    onClick={() => apply({ type: value })}
                                >
                                    {label}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div className="filter-group">
                        <div className="filter-title">{t('catalog.category')}</div>
                        <div className="filter-list">
                            {categories.map((parent) => {
                                /* Раздел раскрыт и когда выбран он сам, и когда
                                   выбран его подраздел: раньше клик по подразделу
                                   схлопывал список, и активный фильтр пропадал
                                   из виду */
                                const childActive = parent.children.some((c) => c.id === filters.category);
                                const open = filters.category === parent.id || childActive;

                                return (
                                    <div key={parent.id}>
                                        <button
                                            className={cn('filter-link', (filters.category === parent.id || childActive) && 'is-active')}
                                            onClick={() => apply({ category: filters.category === parent.id ? null : parent.id })}
                                        >
                                            {parent.name}
                                        </button>
                                        {open && parent.children.length > 0 && (
                                            <div style={{ paddingLeft: 12 }}>
                                                {parent.children.map((child) => (
                                                    <button
                                                        key={child.id}
                                                        className={cn('filter-link t-sm', filters.category === child.id && 'is-active')}
                                                        onClick={() => apply({ category: child.id })}
                                                    >
                                                        {child.name}
                                                    </button>
                                                ))}
                                            </div>
                                        )}
                                    </div>
                                );
                            })}
                        </div>
                    </div>

                    {cities.length > 0 && (
                        <div className="filter-group">
                            <div className="filter-title">{t('catalog.city')}</div>
                            <select
                                className="select"
                                value={filters.city ?? ''}
                                onChange={(e) => apply({ city: e.target.value ? Number(e.target.value) : null })}
                            >
                                <option value="">{t('catalog.city_any')}</option>
                                {cities.map((c) => (
                                    <option key={c.id} value={c.id}>
                                        {c.name}
                                    </option>
                                ))}
                            </select>
                        </div>
                    )}

                    <div className="filter-group">
                        <label className="check">
                            <input
                                type="checkbox"
                                checked={filters.verified}
                                onChange={(e) => apply({ verified: e.target.checked })}
                            />
                            {t('catalog.verified_only')}
                        </label>
                        <label className="check mt-12">
                            <input
                                type="checkbox"
                                checked={filters.with_price}
                                onChange={(e) => apply({ with_price: e.target.checked })}
                            />
                            {t('catalog.with_price')}
                        </label>
                    </div>
                </aside>

                <div className="min-w-0">
                    <div className="section-head-left" style={{ marginBottom: 20 }}>
                        <span className="eyebrow">{t('catalog.eyebrow')}</span>
                        <h1 className="t-section">{t('catalog.h1')}</h1>
                    </div>

                    <div className="toolbar">
                        <div style={{ position: 'relative', flex: 1, minWidth: 220 }}>
                            <label htmlFor="cat-q" className="sr-only">
                                {t('catalog.search_label')}
                            </label>
                            <input
                                id="cat-q"
                                className="input"
                                type="search"
                                placeholder={t('catalog.search_placeholder')}
                                style={{ paddingLeft: 42 }}
                                value={q}
                                onChange={(e) => setQ(e.target.value)}
                                onKeyDown={(e) => e.key === 'Enter' && apply({ q })}
                            />
                            <span
                                aria-hidden
                                style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)', color: 'var(--text-muted)' }}
                            >
                                <Search className="size-5" />
                            </span>
                        </div>

                        <select
                            className="select"
                            style={{ width: 'auto', minWidth: 180 }}
                            aria-label={t('catalog.sort')}
                            value={filters.sort}
                            onChange={(e) => apply({ sort: e.target.value })}
                        >
                            {Object.entries(sorts).map(([key, label]) => (
                                <option key={key} value={key}>
                                    {label}
                                </option>
                            ))}
                        </select>
                    </div>

                    <p className="t-sm muted" style={{ marginBottom: 16 }}>
                        {tChoice('catalog.found', total)}
                    </p>

                    {listings.data.length === 0 ? (
                        <div className="card empty">
                            <div className="empty-icon">
                                <Package aria-hidden className="size-7" />
                            </div>
                            <p className="t-h4">{t('catalog.empty_title')}</p>
                            <p className="t-sm muted mt-8" style={{ maxWidth: 420, margin: '8px auto 0' }}>
                                {t('catalog.empty_text')}
                            </p>
                            <Link href={routes.listingCreate} className="btn btn-primary mt-24">
                                {t('catalog.empty_action')}
                            </Link>
                        </div>
                    ) : (
                        /* Сетка карточек, как в макете новой витрины:
                           фотография, метка NEW, флаг страны, цена и MOQ.
                           Три в ряд — четвёртую колонку съедают фильтры */
                        <div className="product-grid product-grid--catalog">
                            {listings.data.map((row) => (
                                <ProductCard key={row.id} row={row} />
                            ))}
                        </div>
                    )}

                    {listings.last_page > 1 && (
                        <nav className="pagination mt-32" aria-label={t('catalog.pages')}>
                            {listings.links.map((link, i) =>
                                link.url ? (
                                    <Link
                                        key={i}
                                        href={link.url}
                                        className={cn('page-link', link.active && 'is-active')}
                                        aria-current={link.active ? 'page' : undefined}
                                        dangerouslySetInnerHTML={{ __html: link.label }}
                                    />
                                ) : (
                                    /* Недоступная страница — не ссылка: pointer-events
                                       глушит только мышь, а с клавиатуры «#» открывался */
                                    <span
                                        key={i}
                                        className="page-link is-disabled"
                                        aria-disabled="true"
                                        dangerouslySetInnerHTML={{ __html: link.label }}
                                    />
                                ),
                            )}
                        </nav>
                    )}
                </div>
            </div>

            {/* На узком экране фильтры открываются шторкой снизу */}
            <button className="btn btn-primary filter-fab" onClick={() => setFiltersOpen((v) => !v)}>
                {filtersOpen ? <X aria-hidden className="size-4" /> : <SlidersHorizontal aria-hidden className="size-4" />}
                {filtersOpen ? t('catalog.filters_close') : t('catalog.filters')}
            </button>
        </PublicLayout>
    );
}
