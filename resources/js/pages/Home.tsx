import { router } from '@inertiajs/react';
import {
    Armchair,
    ArrowRight,
    Box,
    Boxes,
    Briefcase,
    Cog,
    Cpu,
    FlaskConical,
    Globe2,
    Handshake,
    HardHat,
    Languages,
    Layers,
    MessageSquareText,
    Package,
    Percent,
    Presentation,
    Search,
    Shapes,
    ShieldCheck,
    Shirt,
    Star,
    Truck,
    Users,
    UtensilsCrossed,
    Wallet,
    Wheat,
} from 'lucide-react';
import { useState } from 'react';
import { NewsCover } from '@/components/NewsCover';
import { ProductCard, type ProductRow } from '@/components/ProductCard';
import { VerificationBadge } from '@/components/VerificationBadge';
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

interface CityOption {
    id: number;
    name: string;
}

interface SupplierRow {
    slug: string;
    name: string;
    type_label: string | null;
    city: string | null;
    verification_level: number;
    rating: number;
    reviews_count: number;
    completed_deals_count: number;
    initials: string;
    logo: string | null;
}

interface NewsCard {
    slug: string;
    category: string;
    date: string;
    title: string;
    excerpt: string;
    image: string | null;
}

interface ReviewRow {
    id: number;
    author: string;
    initials: string;
    rating: number;
    body: string;
    when: string;
    company_name: string;
    company_slug: string;
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
    briefcase: Briefcase,
    armchair: Armchair,
    presentation: Presentation,
    truck: Truck,
    other: Shapes,
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
    cities,
}: {
    categories: CategoryTile[];
    countries: CountryOption[];
    cities: CityOption[];
}) {
    const [tab, setTab] = useState<SearchTab>('products');
    const [q, setQ] = useState('');
    const [category, setCategory] = useState('');
    const [country, setCountry] = useState('');
    const [city, setCity] = useState('');

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
        if (city !== '') params.city = Number(city);
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

                <div className="hero-panel-fields">
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
                        <>
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

                            {cities.length > 0 && (
                                <select
                                    className="select"
                                    aria-label={t('home.select_city')}
                                    value={city}
                                    onChange={(e) => setCity(e.target.value)}
                                >
                                    <option value="">{t('home.select_city')}</option>
                                    {cities.map((c) => (
                                        <option key={c.id} value={c.id}>
                                            {c.name}
                                        </option>
                                    ))}
                                </select>
                            )}
                        </>
                    )}

                    {/* Кнопка в одном ряду с селектами — третьей ячейкой,
                        как на утверждённом макете */}
                    <button type="submit" className="btn btn-primary hero-panel-submit">
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
    requests,
    suppliers,
    countries,
    cities,
    news,
    reviews,
    heroImage,
}: {
    stats: Stats;
    categories: CategoryTile[];
    latest: ProductRow[];
    requests: ProductRow[];
    suppliers: SupplierRow[];
    countries: CountryOption[];
    cities: CityOption[];
    news: NewsCard[];
    /** Фон первого экрана — задаётся в админке, разделе «Оформление» */
    heroImage: string;
    reviews: ReviewRow[];
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
            overlayHeader
        >
            {/* ── Первый экран: тёмно-синий порт ── */}
            {/* Фон приходит с сервера: картинку меняют в админке,
                и пересобирать стили ради этого незачем. Затемнение
                и цвет подложки остаются в CSS */}
            <section className="hero-b2b hero-b2b--underlay" style={{ backgroundImage: `url(${heroImage})` }}>
                <div className="container">
                    <div className="hero-b2b-inner">
                        {/* Текст занимает левую половину — фотография
                            остаётся открытой справа, панель ниже на всю
                            ширину: композиция утверждённого макета */}
                        <div className="hero-b2b-copy" data-reveal>
                            <h1>{t('home.h1')}</h1>
                            <p className="hero-b2b-lead">{t('home.lead')}</p>
                            {/* «Продавцы» — предложения товаров, «Покупатели» —
                                запросы на закупку: две стороны площадки */}
                            <div className="hero-b2b-cta">
                                <Link href={routes.catalog} className="btn btn-primary btn-lg">
                                    {t('home.cta_products')}
                                </Link>
                                <Link href={`${routes.catalog}?type=demand`} className="btn btn-secondary btn-lg">
                                    {t('home.cta_companies')}
                                </Link>
                            </div>
                        </div>

                        <HeroSearch categories={categories} countries={countries} cities={cities} />
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
                <section className="section--tight">
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
                <section className="section--tight">
                    <div className="container">
                        <div className="section-bar">
                            <h2>{t('home.latest_title')}</h2>
                            <Link href={routes.catalog} className="section-bar-link">
                                {t('home.latest_all')} <ArrowRight aria-hidden className="go-arrow size-4" />
                            </Link>
                        </div>
                        <div className="card-row" data-reveal-stagger>
                            {latest.map((row) => (
                                <ProductCard key={row.id} row={row} />
                            ))}
                        </div>
                    </div>
                </section>
            )}

            {/* ── Запросы (RFQ): другая сторона площадки — «куплю».
                 Лента горизонтальной прокруткой в один ряд, чтобы
                 не спорить с сеткой товаров выше ── */}
            {requests.length > 0 && (
                <section className="section--tight">
                    <div className="container">
                        <div className="section-bar">
                            <h2>{t('home.requests_title')}</h2>
                            <Link href={`${routes.catalog}?type=demand`} className="section-bar-link">
                                {t('home.requests_all')} <ArrowRight aria-hidden className="go-arrow size-4" />
                            </Link>
                        </div>
                        <div className="card-row" data-reveal-stagger>
                            {requests.map((row) => (
                                <ProductCard key={row.id} row={row} />
                            ))}
                        </div>
                    </div>
                </section>
            )}

            {/* ── Поставщики: покупатель фильтруется по блокам — кто ищет
                 товар, остаётся выше, кто ищет партнёра — здесь ── */}
            {suppliers.length > 0 && (
                <section className="section--tight">
                    <div className="container">
                        <div className="section-bar">
                            <h2>{t('home.suppliers_title')}</h2>
                            <Link href={routes.companies} className="section-bar-link">
                                {t('home.suppliers_all')} <ArrowRight aria-hidden className="go-arrow size-4" />
                            </Link>
                        </div>
                        <div className="supplier-grid" data-reveal-stagger>
                            {suppliers.map((s) => (
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
                                        <span>{tChoice('home.suppliers_deals', s.completed_deals_count)}</span>
                                    </span>
                                </Link>
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
                </div>
            </section>

            {/* ── Отзывы пользователей: живые, из базы — выдуманные
                 цитаты на витрине недопустимы, как и счётчики ── */}
            {reviews.length > 0 && (
                <section className="section">
                    <div className="container">
                        <div className="section-bar">
                            <h2>{t('home.reviews_title')}</h2>
                        </div>
                        <div className="review-grid" data-reveal-stagger>
                            {reviews.map((r) => (
                                <article key={r.id} className="review-card">
                                    <span className="row" style={{ gap: 2 }} aria-label={`${r.rating}/5`}>
                                        {[1, 2, 3, 4, 5].map((i) => (
                                            <Star
                                                key={i}
                                                aria-hidden
                                                className="size-4"
                                                fill={i <= r.rating ? 'var(--warning)' : 'none'}
                                                color={i <= r.rating ? 'var(--warning)' : 'var(--border-strong)'}
                                            />
                                        ))}
                                    </span>
                                    <p className="review-body">{r.body}</p>
                                    <div className="review-foot">
                                        <span className="avatar-sm" aria-hidden>
                                            {r.initials}
                                        </span>
                                        <span style={{ minWidth: 0 }}>
                                            <b className="t-sm" style={{ display: 'block' }}>
                                                {r.author}
                                            </b>
                                            <Link
                                                href={routes.company(r.company_slug)}
                                                className="review-company"
                                            >
                                                {t('home.reviews_about', { name: r.company_name })}
                                            </Link>
                                        </span>
                                        <span className="t-xs" style={{ marginLeft: 'auto', flexShrink: 0 }}>
                                            {r.when}
                                        </span>
                                    </div>
                                </article>
                            ))}
                        </div>
                    </div>
                </section>
            )}

            {/* ── Частые вопросы: карточки вместо аккордеона — ответ
                 виден сразу, без клика. Нумерация вопросов совпадает
                 с разметкой FAQPage в PageController::home ── */}
            <section className="section">
                <div className="container">
                    <div className="section-bar">
                        <h2>{t('home.objections_title')}</h2>
                    </div>
                    <div className="objection-grid" data-reveal-stagger>
                        {(
                            [
                                [Wallet, 1],
                                [Percent, 2],
                                [ShieldCheck, 3],
                                [MessageSquareText, 4],
                                [Users, 5],
                                [Languages, 6],
                            ] as const
                        ).map(([Icon, i]) => (
                            <div key={i} className="objection-card">
                                <span className="objection-ico">
                                    <Icon aria-hidden className="size-6" />
                                </span>
                                <div>
                                    <h3 className="t-h4">{t(`home.faq_q${i}`)}</h3>
                                    <p>{t(`home.faq_a${i}`)}</p>
                                </div>
                            </div>
                        ))}
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
                        <div className="news-grid" data-reveal-stagger>
                            {news.map((p) => (
                                <Link
                                    key={p.slug}
                                    href={routes.newsPost(p.slug)}
                                    className="card lift"
                                    style={{ padding: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', color: 'inherit' }}
                                >
                                    <NewsCover category={p.category} image={p.image} />
                                    <div style={{ padding: 14, display: 'flex', flexDirection: 'column', flex: 1 }}>
                                        {/* Одна строка без переноса: перенос ломал бы
                                            выравнивание заголовков между карточками */}
                                        <div className="row" style={{ gap: 8, marginBottom: 10, flexWrap: 'nowrap', overflow: 'hidden' }}>
                                            <span className="badge badge-neutral">{p.category}</span>
                                            <span className="t-caption muted" style={{ whiteSpace: 'nowrap' }}>{p.date}</span>
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
