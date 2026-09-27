import { router } from '@inertiajs/react';
import {
    Armchair,
    ArrowRight,
    Box,
    Calculator,
    Boxes,
    Briefcase,
    Cog,
    Code2,
    Cpu,
    FileCheck2,
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
    UserSearch,
    Users,
    UtensilsCrossed,
    Wallet,
    Wheat,
} from 'lucide-react';
import { useState } from 'react';
import { NewsCover } from '@/components/NewsCover';
import { BannerSlot, type BannerData } from '@/components/BannerSlot';
import { CardRow } from '@/components/CardRow';
import { ProductCard, type ProductRow } from '@/components/ProductCard';
import { ReviewCard, type FeedReview } from '@/components/ReviewCard';
import { SelectField } from '@/components/SelectField';
import { VerificationBadge } from '@/components/VerificationBadge';
import { formatNumber } from '@/components/cabinet';
import { Link } from '@/components/ui/Link';
import { PublicLayout } from '@/layouts/PublicLayout';
import { cn } from '@/lib/cn';
import { t, tChoice } from '@/lib/i18n';
import { routes } from '@/routes';

/**
 * Секция главной: тексты и видимость из админки («Главная страница»),
 * уже на языке посетителя (LandingBlock::card). Порядок секций задан
 * макетом, а не админкой.
 */
interface Block {
    visible: boolean;
    eyebrow: string;
    heading: string;
    subheading: string;
    button: string;
    /** Пункты «Как это работает» и «Частых вопросов» */
    items?: { title: string; text: string }[];
    /** Подпись под кнопкой призыва */
    note?: string;
}

const EMPTY_BLOCK: Block = { visible: true, eyebrow: '', heading: '', subheading: '', button: '', items: [], note: '' };

/** Иконки карточек вопросов — по порядку, дальше по кругу. */
const FAQ_ICONS = [Wallet, Percent, ShieldCheck, MessageSquareText, Users, Languages];

interface Stats {
    companies: number;
    listings: number;
    categories: number;
    countries: number;
}

/** Направление «Доп. услуг» для плитки рядом с категориями */
interface ServiceTile {
    type: string;
    name: string;
    tasks: number;
}

/** Адрес раздела «Другое» в каталоге (CategorySeeder) */
const OTHER_CATEGORY_SLUG = 'drugoe';

const SERVICE_ICONS: Record<string, typeof Package> = {
    it: Code2,
    logistics: Truck,
    hr_services: UserSearch,
    customs: FileCheck2,
    accounting: Calculator,
};

interface CategoryTile {
    id: number;
    slug: string;
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
    listings_count: number;
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
                        <SelectField
                            ariaLabel={t('home.select_country')}
                            placeholder={t('home.select_country')}
                            value={country}
                            onChange={setCountry}
                            options={countries.map((c) => ({ value: c.code, label: c.name }))}
                        />
                    ) : (
                        <>
                            <SelectField
                                ariaLabel={t('home.select_category')}
                                placeholder={t('home.select_category')}
                                value={category}
                                onChange={setCategory}
                                options={categories.map((c) => ({ value: String(c.id), label: c.name }))}
                            />

                            {cities.length > 0 && (
                                <SelectField
                                    ariaLabel={t('home.select_city')}
                                    placeholder={t('home.select_city')}
                                    value={city}
                                    onChange={setCity}
                                    options={cities.map((c) => ({ value: String(c.id), label: c.name }))}
                                />
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
    blocks,
    stats,
    categories,
    services,
    latest,
    requests,
    suppliers,
    countries,
    cities,
    news,
    reviews,
    heroImage,
    banner,
}: {
    blocks: Partial<Record<string, Block>>;
    stats: Stats;
    categories: CategoryTile[];
    /** Две популярные услуги — плитки рядом с категориями */
    services: ServiceTile[];
    latest: ProductRow[];
    requests: ProductRow[];
    suppliers: SupplierRow[];
    countries: CountryOption[];
    cities: CityOption[];
    news: NewsCard[];
    /** Фон первого экрана — задаётся в админке, разделе «Оформление» */
    heroImage: string;
    /** Пропорции кадра (ширина/высота); null — фон из коробки */
    heroRatio: number | null;
    reviews: FeedReview[];
    /** Баннер акции под первым экраном; null — сейчас ничего не идёт */
    banner: BannerData | null;
}) {
    // Каждый счётчик ведёт туда, что он считает: компании — в каталог
    // компаний, объявления и категории — в «Товары», страны — на
    // страницу стран (в шапке её нет, попасть можно отсюда и из подвала)
    const block = (key: string): Block => blocks[key] ?? EMPTY_BLOCK;
    const shown = (key: string): boolean => block(key).visible;
    const hero = block('hero');
    const how = block('how');
    const faq = block('faq');
    const blog = block('news');
    const cta = block('cta');

    const statCells: [typeof Users, string, number, string, string][] = [
        [Users, 'stat-ico-blue', stats.companies, t('home.stat_companies'), routes.companies],
        [Boxes, 'stat-ico-orange', stats.listings, t('home.stat_listings'), routes.catalog],
        [Globe2, 'stat-ico-sky', stats.countries, t('home.stat_countries'), routes.countries],
        [Handshake, 'stat-ico-violet', stats.categories, t('home.stat_categories'), routes.catalog],
    ];

    // Раздел «Другое» ничего не говорит о товаре, поэтому стоит
    // в конце ряда, после плиток услуг
    const otherCategory = categories.find((c) => c.slug === OTHER_CATEGORY_SLUG);
    const mainCategories = categories
        .filter((c) => c !== otherCategory)
        .slice(0, Math.max(0, 6 - services.length - (otherCategory ? 1 : 0)));

    // Цвет плитки — по месту раздела в каталоге: у «Другого» он
    // не меняется от того, что плитка переехала в конец ряда
    const categoryTile = (c: CategoryTile) => {
        const Icon = categoryIcon(c.icon);

        return (
            <Link key={c.id} href={`${routes.catalog}?category=${c.id}`} className="cat-card">
                <span className={cn('cat-thumb', `cat-g-${(categories.indexOf(c) % 8) + 1}`)}>
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
    };

    return (
        <PublicLayout
            /*
             * Заголовок и описание — те же строки, что печатает сервер
             * в <title> и <meta name="description">. Раньше у главной
             * были свои home.meta_*, и тексты разошлись: в выдаче Google
             * заголовок оказался клиентский, а описание серверное —
             * страница представлялась двумя разными фразами.
             */
            title={t('seo.home_title')}
            description={t('seo.home_description')}
            overlayHeader
        >
            {/* ── Первый экран: тёмно-синий порт ── */}
            {/* Фон приходит с сервера: картинку меняют в админке,
                и пересобирать стили ради этого незачем. Затемнение
                и цвет подложки остаются в CSS.

                Высота первого экрана фиксированная (см. CSS), кадр
                ложится cover по центру — фото не диктует высоту */}
            <section className="hero-b2b hero-b2b--underlay" style={{ backgroundImage: `url(${heroImage})` }}>
                <div className="container">
                    <div className="hero-b2b-inner">
                        {/* Текст занимает левую половину — фотография
                            остаётся открытой справа, панель ниже на всю
                            ширину: композиция утверждённого макета */}
                        <div className="hero-b2b-copy" data-reveal>
                            <h1>{hero.heading}</h1>
                            {hero.subheading !== '' && <p className="hero-b2b-lead">{hero.subheading}</p>}
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
                    </div>
                </div>
            </section>

            {/* ── Поиск под фотографией: панель стоит на подложке
                 страницы, а не поверх кадра — картинка остаётся целой ── */}
            <section className="hero-search-band">
                <div className="container">
                    <HeroSearch categories={categories} countries={countries} cities={cities} />
                </div>
            </section>

            {/* ── Баннер акции: заводится из админки, срок задаётся там же.
                 Место не резервируется — нет акции, нет и пустоты ── */}
            <div className="container">
                <BannerSlot banner={banner} />
            </div>

            {/* ── Показатели: цифры из базы — выдуманные счётчики
                 на витрине недопустимы ── */}
            {shown('stats') && (
                <section className="stats-band">
                    <div className="container">
                        <div className="stats-band-card">
                            {statCells.map(([Icon, tone, value, label, href]) => (
                                <Link key={label} href={href} className="stat-cell">
                                    <span className={cn('stat-ico', tone)}>
                                        <Icon aria-hidden className="size-5" />
                                    </span>
                                    <div style={{ minWidth: 0 }}>
                                        <div className="stat-cell-num">{formatNumber(value)}</div>
                                        <div className="stat-cell-label">{label}</div>
                                    </div>
                                </Link>
                            ))}
                        </div>
                    </div>
                </section>
            )}

            {/* ── Популярные категории ── */}
            {shown('categories') && (categories.length > 0 || services.length > 0) && (
                <section className="section--tight">
                    <div className="container">
                        <div className="section-bar">
                            <h2>{block('categories').heading}</h2>
                            <Link href={routes.catalog} className="section-bar-link">
                                {t('home.categories_all')} <ArrowRight aria-hidden className="go-arrow size-4" />
                            </Link>
                        </div>
                        <div className="cat-grid" data-reveal-stagger>
                            {/* Ряд — шесть плиток: разделы каталога, за ними
                                услуги, «Другое» — последним */}
                            {mainCategories.map(categoryTile)}
                            {services.map((svc, i) => {
                                const Icon = SERVICE_ICONS[svc.type] ?? Briefcase;

                                return (
                                    <Link
                                        key={svc.type}
                                        href={`${routes.itTasks}?type=${svc.type}`}
                                        className="cat-card"
                                    >
                                        <span className={cn('cat-thumb', `cat-g-${i === 0 ? 7 : 8}`)}>
                                            <Icon aria-hidden />
                                        </span>
                                        <span style={{ minWidth: 0 }}>
                                            <span className="cat-name">{svc.name}</span>
                                            <span className="cat-count" style={{ display: 'block' }}>
                                                {svc.tasks > 0 ? tChoice('it_tasks.found', svc.tasks) : t('nav.it_services')}
                                            </span>
                                        </span>
                                    </Link>
                                );
                            })}
                            {otherCategory && categoryTile(otherCategory)}
                        </div>
                    </div>
                </section>
            )}

            {/* ── Витрина VIP: объявления компаний с высшим тарифом ── */}
            {shown('vip') && latest.length > 0 && (
                <section className="section--tight">
                    <div className="container">
                        <div className="section-bar">
                            <h2>{block('vip').heading}</h2>
                            <Link href={routes.catalog} className="section-bar-link">
                                {t('home.latest_all')} <ArrowRight aria-hidden className="go-arrow size-4" />
                            </Link>
                        </div>
                        <CardRow>
                            {latest.map((row) => (
                                <ProductCard key={row.id} row={row} />
                            ))}
                        </CardRow>
                    </div>
                </section>
            )}

            {/* ── Запросы (RFQ): другая сторона площадки — «куплю».
                 Лента горизонтальной прокруткой в один ряд, чтобы
                 не спорить с сеткой товаров выше ── */}
            {shown('requests') && requests.length > 0 && (
                <section className="section--tight">
                    <div className="container">
                        <div className="section-bar">
                            <h2>{block('requests').heading}</h2>
                            <Link href={`${routes.catalog}?type=demand`} className="section-bar-link">
                                {t('home.requests_all')} <ArrowRight aria-hidden className="go-arrow size-4" />
                            </Link>
                        </div>
                        <CardRow>
                            {requests.map((row) => (
                                <ProductCard key={row.id} row={row} />
                            ))}
                        </CardRow>
                    </div>
                </section>
            )}

            {/* ── Поставщики: покупатель фильтруется по блокам — кто ищет
                 товар, остаётся выше, кто ищет партнёра — здесь ── */}
            {shown('suppliers') && suppliers.length > 0 && (
                <section className="section--tight">
                    <div className="container">
                        <div className="section-bar">
                            <h2>{block('suppliers').heading}</h2>
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
                                        <span>{tChoice('home.suppliers_listings', s.listings_count)}</span>
                                    </span>
                                </Link>
                            ))}
                        </div>
                    </div>
                </section>
            )}

            {/* ── Как это работает ── */}
            {shown('how') && (
                <section className="section-lg section--white">
                    <div className="container">
                        <div className="section-head-left">
                            {how.eyebrow !== '' && <span className="eyebrow">{how.eyebrow}</span>}
                            <h2 className="t-section">{how.heading}</h2>
                            {how.subheading !== '' && <p className="t-lead">{how.subheading}</p>}
                        </div>
                        <div className="flow" data-reveal-stagger>
                            {(how.items ?? []).map((step, i) => (
                                <div key={i} className="flow-step">
                                    <div className="flow-num">{i + 1}</div>
                                    <h4 className="t-h4">{step.title}</h4>
                                    <p>{step.text}</p>
                                </div>
                            ))}
                        </div>
                    </div>
                </section>
            )}

            {/* ── Отзывы пользователей: живые, из базы — выдуманные
                 цитаты на витрине недопустимы, как и счётчики. Три
                 свежих — о компаниях и о площадке; остальные — на /reviews ── */}
            {shown('reviews') && reviews.length > 0 && (
                <section className="section">
                    <div className="container">
                        <div className="section-bar">
                            <h2>{block('reviews').heading}</h2>
                            <Link href={routes.reviews} className="section-bar-link">
                                {t('home.reviews_all')} <ArrowRight aria-hidden className="go-arrow size-4" />
                            </Link>
                        </div>
                        <div className="review-grid" data-reveal-stagger>
                            {reviews.map((r) => (
                                <ReviewCard key={`${r.kind}-${r.id}`} review={r} />
                            ))}
                        </div>
                    </div>
                </section>
            )}

            {/* ── Частые вопросы: карточки вместо аккордеона — ответ
                 виден сразу, без клика. Те же вопросы размечены для
                 поисковика (FAQPage в PageController::home) ── */}
            {shown('faq') && (faq.items ?? []).length > 0 && (
                <section className="section">
                    <div className="container">
                        <div className="section-bar">
                            <h2>{faq.heading}</h2>
                        </div>
                        <div className="objection-grid" data-reveal-stagger>
                            {(faq.items ?? []).map((item, i) => {
                                const Icon = FAQ_ICONS[i % FAQ_ICONS.length];

                                return (
                                    <div key={i} className="objection-card">
                                        <span className="objection-ico">
                                            <Icon aria-hidden className="size-6" />
                                        </span>
                                        <div>
                                            <h3 className="t-h4">{item.title}</h3>
                                            <p>{item.text}</p>
                                        </div>
                                    </div>
                                );
                            })}
                        </div>
                    </div>
                </section>
            )}

            {/* ── Новости ── */}
            {shown('news') && news.length > 0 && (
                <section className="section-lg">
                    <div className="container">
                        <div className="row-between wrap" style={{ alignItems: 'flex-end', marginBottom: 36 }}>
                            <div className="section-head-left" style={{ marginBottom: 0 }}>
                                {blog.eyebrow !== '' && <span className="eyebrow">{blog.eyebrow}</span>}
                                <h2 className="t-section">{blog.heading}</h2>
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
            {shown('cta') && (
                <section className="section--tight">
                    <div className="container">
                        <div className="cta-band">
                            <h2 className="t-h1">{cta.heading}</h2>
                            {cta.subheading !== '' && <p className="t-lead">{cta.subheading}</p>}
                            <Link
                                href={routes.register}
                                className="btn btn-lg"
                                style={{ background: '#fff', color: 'var(--primary-700)' }}
                            >
                                {cta.button}
                            </Link>
                            {cta.note !== '' && <p className="cta-note">{cta.note}</p>}
                        </div>
                    </div>
                </section>
            )}
        </PublicLayout>
    );
}
