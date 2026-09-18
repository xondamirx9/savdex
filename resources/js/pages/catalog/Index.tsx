import { router } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { Building2, Package, Search, SlidersHorizontal, X } from 'lucide-react';
import { useState } from 'react';
import { ProductCard, type ProductRow } from '@/components/ProductCard';
import { SelectField } from '@/components/SelectField';
import { TenderCard, type TenderRow } from '@/components/TenderCard';
import { PublicLayout } from '@/layouts/PublicLayout';
import { cn } from '@/lib/cn';
import { t, tChoice } from '@/lib/i18n';
import { routes } from '@/routes';

interface Page<Row> {
    data: Row[];
    links: { url: string | null; label: string; active: boolean }[];
    current_page: number;
    last_page: number;
}

interface Props {
    /** Лента объявлений; на вкладке тендеров её нет */
    listings?: Page<ProductRow>;
    /** Лента тендеров; приходит только на своей вкладке */
    tenders?: Page<TenderRow>;
    filters: {
        q: string;
        type: string;
        category: number | null;
        city: number | null;
        verified: boolean;
        with_price: boolean;
        sort: string;
        /** Состояние приёма заявок — только у тендеров */
        closed: boolean;
    };
    sorts: Record<string, string>;
    categories: { id: number; name: string; children: { id: number; name: string }[] }[];
    cities: { id: number; name: string }[];
    total: number;
}

/**
 * Каталог: объявления и тендеры на одной странице.
 *
 * Тендер лежит в своей таблице и карточка у него своя, но ищут его
 * там же, где запросы на закупку, — поэтому он не отдельный раздел,
 * а вкладка того же фильтра. Фильтров у тендера меньше: города,
 * проверенной компании и цены у закупки нет, и показывать их
 * неработающими хуже, чем не показывать.
 */
export default function CatalogIndex({ listings, tenders, filters, sorts, categories, cities, total }: Props) {
    const [q, setQ] = useState(filters.q);
    const [filtersOpen, setFiltersOpen] = useState(false);

    const isTenders = filters.type === 'tender';
    const feed = isTenders ? tenders : listings;

    function apply(next: Partial<Props['filters']>) {
        /*
         * При переходе на тендеры отборы, которых у закупки нет,
         * снимаются: адрес с «?type=tender&city=5» обещал бы фильтр,
         * которого не будет, и при возврате к объявлениям срабатывал бы
         * неожиданно. Обратный переход снимает состояние заявок.
         */
        const switching = next.type !== undefined && next.type !== filters.type;
        const cleared = switching
            ? next.type === 'tender'
                ? { city: null, verified: false, with_price: false }
                : { closed: false }
            : {};

        router.get(
            routes.catalog,
            // Пустые значения выкидываются: адрес с «?type=&city=»
            // невозможно ни прочитать, ни переслать коллеге
            Object.fromEntries(
                Object.entries({ ...filters, ...next, ...cleared }).filter(
                    ([, v]) => v !== '' && v !== null && v !== false,
                ),
            ),
            { preserveState: true, preserveScroll: true, replace: true },
        );
    }

    const hasFilters =
        filters.type !== '' || filters.category !== null || filters.city !== null ||
        filters.verified || filters.with_price || filters.closed;

    return (
        <PublicLayout
            title={t(isTenders ? 'tenders.meta_title' : 'catalog.meta_title')}
            description={t(isTenders ? 'tenders.meta_description' : 'catalog.meta_description')}
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
                                    // Закупки внешних заказчиков — здесь же:
                                    // их ищут вместе с запросами компаний
                                    ['tender', t('catalog.type_tender')],
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

                        {/* Приём заявок — состояние того же списка,
                            поэтому под вкладками, а не отдельной группой */}
                        {isTenders && (
                            <div className="row wrap mt-12" style={{ gap: 6 }}>
                                <button
                                    className={cn('chip', !filters.closed && 'chip-active')}
                                    aria-pressed={!filters.closed}
                                    onClick={() => apply({ closed: false })}
                                >
                                    {t('tenders.tab_open')}
                                </button>
                                <button
                                    className={cn('chip', filters.closed && 'chip-active')}
                                    aria-pressed={filters.closed}
                                    onClick={() => apply({ closed: true })}
                                >
                                    {t('tenders.tab_closed')}
                                </button>
                            </div>
                        )}
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

                    {cities.length > 0 && ! isTenders && (
                        <div className="filter-group">
                            <div className="filter-title">{t('catalog.city')}</div>
                            <SelectField
                                ariaLabel={t('catalog.city')}
                                placeholder={t('catalog.city_any')}
                                value={filters.city === null ? '' : String(filters.city)}
                                onChange={(v) => apply({ city: v === '' ? null : Number(v) })}
                                options={cities.map((c) => ({ value: String(c.id), label: c.name }))}
                            />
                        </div>
                    )}

                    {/* У закупки нет ни проверенной компании, ни цены:
                        неработающая галочка хуже её отсутствия */}
                    <div className="filter-group" hidden={isTenders}>
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
                        <span className="eyebrow">{t(isTenders ? 'tenders.eyebrow' : 'catalog.eyebrow')}</span>
                        <h1 className="t-section">{t(isTenders ? 'tenders.h1' : 'catalog.h1')}</h1>
                        {isTenders && <p className="t-body muted">{t('tenders.lead')}</p>}
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
                                placeholder={t(isTenders ? 'tenders.search_placeholder' : 'catalog.search_placeholder')}
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

                        {/* Сортировка без пункта «любая»: пустого значения
                            у неё не бывает, список всегда на чём-то стоит.
                            У тендеров её нет: они всегда идут по сроку
                            подачи — сначала те, до которых ближе */}
                        {! isTenders && <SelectField
                            className="select-field--auto"
                            ariaLabel={t('catalog.sort')}
                            value={filters.sort}
                            onChange={(sort) => apply({ sort })}
                            options={Object.entries(sorts).map(([key, label]) => ({ value: key, label }))}
                        />}
                    </div>

                    <p className="t-sm muted" style={{ marginBottom: 16 }}>
                        {tChoice(isTenders ? 'tenders.found' : 'catalog.found', total)}
                    </p>

                    {feed === undefined || feed.data.length === 0 ? (
                        <div className="card empty">
                            <div className="empty-icon">
                                {isTenders
                                    ? <Building2 aria-hidden className="size-7" />
                                    : <Package aria-hidden className="size-7" />}
                            </div>
                            <p className="t-h4">{t(isTenders ? 'tenders.empty_title' : 'catalog.empty_title')}</p>
                            <p className="t-sm muted mt-8" style={{ maxWidth: 420, margin: '8px auto 0' }}>
                                {t(isTenders ? 'tenders.empty_text' : 'catalog.empty_text')}
                            </p>
                            {/* Разместить можно объявление: тендеры заводит
                                площадка, кнопка вела бы не туда */}
                            {! isTenders && (
                                <Link href={routes.listingCreate} className="btn btn-primary mt-24">
                                    {t('catalog.empty_action')}
                                </Link>
                            )}
                        </div>
                    ) : isTenders ? (
                        <div className="grid grid-3" data-reveal-stagger>
                            {(feed as Page<TenderRow>).data.map((row) => (
                                <TenderCard key={row.id} row={row} />
                            ))}
                        </div>
                    ) : (
                        /* Сетка карточек, как в макете новой витрины:
                           фотография, метка NEW, флаг страны, цена и MOQ.
                           Три в ряд — четвёртую колонку съедают фильтры */
                        <div className="product-grid product-grid--catalog">
                            {(feed as Page<ProductRow>).data.map((row) => (
                                <ProductCard key={row.id} row={row} />
                            ))}
                        </div>
                    )}

                    {feed !== undefined && feed.last_page > 1 && (
                        <nav className="pagination mt-32" aria-label={t('catalog.pages')}>
                            {feed.links.map((link, i) =>
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
