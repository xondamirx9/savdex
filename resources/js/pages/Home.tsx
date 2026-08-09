import { router } from '@inertiajs/react';
import {
    ArrowRight,
    Box,
    Boxes,
    Cog,
    Cpu,
    FlaskConical,
    Globe2,
    Handshake,
    HardHat,
    Layers,
    Package,
    Search,
    Shield,
    Shirt,
    UtensilsCrossed,
    Users,
    Wheat,
} from 'lucide-react';
import { useState } from 'react';
import { NewsCover } from '@/components/NewsCover';
import { ProductCard, type ProductRow } from '@/components/ProductCard';
import { formatNumber } from '@/components/cabinet';
import { Link } from '@/components/ui/Link';
import { PublicLayout } from '@/layouts/PublicLayout';
import { cn } from '@/lib/cn';
import { t, tChoice } from '@/lib/i18n';
import { routes } from '@/routes';

/*
 * Списки собираются функциями, а не константами модуля: подписи
 * берутся из словаря, а он приходит с сервером — константа
 * вычислилась бы до того, как словарь установлен.
 */
const steps = (): [string, string][] =>
    [1, 2, 3, 4].map((i) => [t(`home.step${i}_title`), t(`home.step${i}_text`)]);

interface Stats {
    companies: number;
    listings: number;
    categories: number;
    countries: number;
    deals: number;
}

interface CategoryTile {
    id: number;
    name: string;
    icon: string | null;
    listings: number;
}

interface CountryOption {
    code: string;
    name: string;
}

interface NewsCard {
    slug: string;
    category: string;
    date: string;
    title: string;
    excerpt: string;
    image: string | null;
}

/**
 * Значок раздела каталога.
 *
 * Ключи — значения поля icon из справочника категорий; неизвестный
 * ключ получает коробку: раздел без значка — не повод ломать плитку.
 */
const CATEGORY_ICONS: Record<string, typeof Package> = {
    // Значки из справочника (CategorySeeder)
    package: HardHat,
    shirt: Shirt,
    layers: Layers,
    wheat: Wheat,
    box: Box,
    settings: Cog,
    // Запасные соответствия на случай новых разделов из админки
    textile: Shirt,
    food: UtensilsCrossed,
    construction: HardHat,
    electronics: Cpu,
    machinery: Cog,
    chemistry: FlaskConical,
    chemicals: FlaskConical,
};

function categoryIcon(icon: string | null): typeof Package {
    if (!icon) return Package;

    return CATEGORY_ICONS[icon] ?? Package;
}

type SearchTab = 'products' | 'companies' | 'rfq';

/**
 * Панель поиска первого экрана: табы «Товары / Компании / Запросы».
 *
 * Товары и запросы ищутся в каталоге (запрос — тот же каталог
 * с типом «спрос»), компании — в каталоге компаний с фильтром
 * по стране. Селекты меняются вместе с табом: стране неоткуда
 * взяться в каталоге товаров, и мёртвый фильтр хуже отсутствующего.
 */
function HeroSearch({
    categories,
    countries,
}: {
    categories: CategoryTile[];
    countries: CountryOption[];
}) {
    const [tab, setTab] = useState<SearchTab>('products');
    const [q, setQ] = useState('');
    const [category, setCategory] = useState('');
    const [country, setCountry] = useState('');

    function submit(e: React.FormEvent) {
        e.preventDefault();

        if (tab === 'companies') {
            const params: Record<string, string> = {};
            if (q.trim() !== '') params.q = q.trim();
            if (country !== '') params.country = country;
            router.get(routes.companies, params);

            return;
        }

        const params: Record<string, string | number> = {};
        if (q.trim() !== '') params.q = q.trim();
        if (category !== '') params.category = Number(category);
        if (tab === 'rfq') params.type = 'demand';
        router.get(routes.catalog, params);
    }

    const tabs: [SearchTab, string][] = [
        ['products', t('home.tab_products')],
        ['companies', t('home.tab_companies')],
        ['rfq', t('home.tab_rfq')],
    ];

    return (
        <div className="hero-panel">
            <div className="hero-tabs" role="tablist">
                {tabs.map(([key, label]) => (
                    <button
                        key={key}
                        role="tab"
                        aria-selected={tab === key}
                        className="hero-tab"
                        onClick={() => setTab(key)}
                    >
                        {label}
                    </button>
                ))}
            </div>

            <form role="search" onSubmit={submit}>
                <label htmlFor="hero-q" className="sr-only">
                    {t('home.search_label')}
                </label>
                <input
                    id="hero-q"
                    className="input"
                    type="search"
                    placeholder={`${t('home.search_label')}?`}
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                />

                <div className="hero-panel-row">
                    {tab === 'companies' ? (
                        <select
                            className="select"
                            aria-label={t('home.select_country')}
                            value={country}
                            onChange={(e) => setCountry(e.target.value)}
                        >
                            <option value="">{t('home.select_country')}</option>
                            {countries.map((c) => (
                                <option key={c.code} value={c.code}>
                                    {c.name}
                                </option>
                            ))}
                        </select>
                    ) : (
                        <select
                            className="select"
                            aria-label={t('home.select_category')}
                            value={category}
                            onChange={(e) => setCategory(e.target.value)}
                        >
                            <option value="">{t('home.select_category')}</option>
                            {categories.map((c) => (
                                <option key={c.id} value={c.id}>
                                    {c.name}
                                </option>
                            ))}
                        </select>
                    )}

                    <button type="submit" className="btn btn-primary">
                        <Search aria-hidden className="size-4" /> {t('home.search_button')}
                    </button>
                </div>

                {categories.length > 0 && (
                    <div className="hero-chips">
                        <span>{t('home.popular')}:</span>
                        {categories.slice(0, 4).map((c) => (
                            <Link key={c.id} href={`${routes.catalog}?category=${c.id}`}>
                                {c.name}
                            </Link>
                        ))}
                    </div>
                )}
            </form>
        </div>
    );
}

export default function Home({
    stats,
    categories,
    latest,
    countries,
    news,
}: {
    stats: Stats;
    categories: CategoryTile[];
    latest: ProductRow[];
    countries: CountryOption[];
    news: NewsCard[];
}) {
    const statCells: [typeof Users, string, number, string][] = [
        [Users, 'stat-ico-blue', stats.companies, t('home.stat_companies')],
        [Boxes, 'stat-ico-orange', stats.listings, t('home.stat_listings')],
        [Globe2, 'stat-ico-sky', stats.countries, t('home.stat_countries')],
        [Handshake, 'stat-ico-violet', stats.deals, t('home.stat_deals')],
    ];

    return (
        <PublicLayout
            title={t('home.meta_title')}
            description={t('home.meta_description')}
        >
            {/* ── Первый экран: тёмно-синий порт ── */}
            <section className="hero-b2b">
                <div className="container">
                    <div className="hero-b2b-inner">
                        <div data-reveal>
                            <h1>{t('home.h1')}</h1>
                            <p className="hero-b2b-lead">{t('home.lead')}</p>
                            <div className="hero-b2b-cta">
                                <Link href={routes.catalog} className="btn btn-primary btn-lg">
                                    {t('home.cta_products')}
                                </Link>
                                <Link href={routes.companies} className="btn btn-secondary btn-lg">
                                    {t('home.cta_companies')}
                                </Link>
                            </div>
                        </div>

                        <HeroSearch categories={categories} countries={countries} />
                    </div>
                </div>
            </section>

            {/* ── Показатели: цифры из базы — выдуманные счётчики
                 на витрине недопустимы ── */}
            <section className="stats-band">
                <div className="container">
                    <div className="stats-band-card">
                        {statCells.map(([Icon, tone, value, label]) => (
                            <div key={label} className="stat-cell">
                                <span className={cn('stat-ico', tone)}>
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
            </section>

            {/* ── Популярные категории ── */}
            {categories.length > 0 && (
                <section className="section--tight" style={{ paddingTop: 44 }}>
                    <div className="container">
                        <div className="section-bar">
                            <h2>{t('home.categories_title')}</h2>
                            <Link href={routes.catalog} className="section-bar-link">
                                {t('home.categories_all')} <ArrowRight aria-hidden className="go-arrow size-4" />
                            </Link>
                        </div>
                        <div className="cat-grid" data-reveal-stagger>
                            {categories.slice(0, 6).map((c, i) => {
                                const Icon = categoryIcon(c.icon);

                                return (
                                    <Link key={c.id} href={`${routes.catalog}?category=${c.id}`} className="cat-card">
                                        <span className={cn('cat-thumb', `cat-g-${(i % 8) + 1}`)}>
                                            <Icon aria-hidden />
                                        </span>
                                        <span style={{ minWidth: 0 }}>
                                            <span className="cat-name">{c.name}</span>
                                            <span className="cat-count" style={{ display: 'block' }}>
                                                {tChoice('home.categories_count', c.listings)}
                                            </span>
                                        </span>
                                    </Link>
                                );
                            })}
                        </div>
                    </div>
                </section>
            )}

            {/* ── Новые объявления ── */}
            {latest.length > 0 && (
                <section className="section--tight" style={{ paddingTop: 8 }}>
                    <div className="container">
                        <div className="section-bar">
                            <h2>{t('home.latest_title')}</h2>
                            <Link href={routes.catalog} className="section-bar-link">
                                {t('home.latest_all')} <ArrowRight aria-hidden className="go-arrow size-4" />
                            </Link>
                        </div>
                        <div className="product-grid" data-reveal-stagger>
                            {latest.map((row) => (
                                <ProductCard key={row.id} row={row} />
                            ))}
                        </div>
                    </div>
                </section>
            )}

            {/* ── Как это работает ── */}
            <section className="section-lg section--white">
                <div className="container">
                    <div className="section-head-left">
                        <span className="eyebrow">{t('home.how_eyebrow')}</span>
                        <h2 className="t-section">{t('home.how_title')}</h2>
                        <p className="t-lead">{t('home.how_lead')}</p>
                    </div>
                    <div className="flow" data-reveal-stagger>
                        {steps().map(([title, text], i) => (
                            <div key={title} className="flow-step">
                                <div className="flow-num">{i + 1}</div>
                                <h4 className="t-h4">{title}</h4>
                                <p>{text}</p>
                            </div>
                        ))}
                    </div>
                    <div className="alert alert-info mt-48">
                        <Shield aria-hidden className="size-5" />
                        <div>
                            <b>{t('home.no_commission_bold')}</b> {t('home.no_commission_text')}
                        </div>
                    </div>
                </div>
            </section>

            {/* ── Новости ── */}
            {news.length > 0 && (
                <section className="section-lg">
                    <div className="container">
                        <div className="row-between wrap" style={{ alignItems: 'flex-end', marginBottom: 36 }}>
                            <div className="section-head-left" style={{ marginBottom: 0 }}>
                                <span className="eyebrow">{t('home.blog_eyebrow')}</span>
                                <h2 className="t-section">{t('home.blog_title')}</h2>
                            </div>
                            <Link href={routes.news} className="btn btn-secondary">
                                {t('home.blog_all')} <ArrowRight aria-hidden className="size-4" />
                            </Link>
                        </div>
                        <div className="grid grid-3" data-reveal-stagger>
                            {news.map((p) => (
                                <Link
                                    key={p.slug}
                                    href={routes.newsPost(p.slug)}
                                    className="card lift"
                                    style={{ padding: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', color: 'inherit' }}
                                >
                                    <NewsCover category={p.category} image={p.image} />
                                    <div style={{ padding: 18, display: 'flex', flexDirection: 'column', flex: 1 }}>
                                        <div className="row wrap" style={{ gap: 8, marginBottom: 10 }}>
                                            <span className="badge badge-neutral">{p.category}</span>
                                            <span className="t-caption muted">{p.date}</span>
                                        </div>
                                        <h3 className="t-h4" style={{ marginBottom: 8 }}>{p.title}</h3>
                                        <p className="t-sm muted" style={{ flex: 1 }}>
                                            {p.excerpt}
                                        </p>
                                        <span className="row mt-16 t-sm" style={{ gap: 6, color: 'var(--primary-700)', fontWeight: 600 }}>
                                            {t('home.blog_read')} <ArrowRight aria-hidden className="go-arrow size-4" />
                                        </span>
                                    </div>
                                </Link>
                            ))}
                        </div>
                    </div>
                </section>
            )}

            {/* ── Финальный призыв ── */}
            <section className="section--tight">
                <div className="container">
                    <div className="cta-band">
                        <h2 className="t-h1">{t('home.cta_title')}</h2>
                        <p className="t-lead">{t('home.cta_lead')}</p>
                        <Link
                            href={routes.register}
                            className="btn btn-lg"
                            style={{ background: '#fff', color: 'var(--primary-700)' }}
                        >
                            {t('home.cta_button')}
                        </Link>
                        <p className="cta-note">{t('home.cta_note')}</p>
                    </div>
                </div>
            </section>
        </PublicLayout>
    );
}
