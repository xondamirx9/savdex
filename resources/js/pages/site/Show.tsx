import { router } from '@inertiajs/react';
import { BadgeCheck, Download, ExternalLink, FileText, Globe, Mail, MapPin, Package, Phone, Send, Star } from 'lucide-react';
import { useEffect, useRef, type CSSProperties, type ReactNode } from 'react';
import { money } from '@/components/ProductCard';
import { formatDecimal, t, tChoice } from '@/lib/i18n';
import { unitLabel } from '@/lib/units';

/**
 * Мини-сайт компании на acme.savdex.site.
 *
 * Вывеска здесь компании, а не площадки: ни шапки, ни меню SAVDEX —
 * только скромная отметка в подвале. Всё оформление держится на
 * CSS-переменных --ms-*, которые собирает сервер (SiteTheme): шаблон
 * решает раскладку, переменные — цвета, шрифты и скругления.
 *
 * Та же страница работает предпросмотром в редакторе кабинета.
 * Там она слушает сообщения от редактора и перекрашивается частичной
 * перезагрузкой: переменные снова считает сервер, и цвет, который
 * компания увидит в редакторе, совпадёт с тем, что увидят клиенты.
 */

export type SiteTheme = {
    template: 'classic' | 'bold' | 'minimal';
    primary: string;
    accent: string;
    mode: 'light' | 'dark';
    heading_font: string;
    body_font: string;
    radius: 'sharp' | 'soft' | 'round';
    /** Загруженный фон первого экрана: путь в хранилище */
    hero_image: string | null;
};

/** Сообщение редактора предпросмотру. */
export const THEME_MESSAGE = 'savdex:site-theme';

type Company = {
    name: string;
    legal_name: string | null;
    type_label: string | null;
    custom_category: string | null;
    country: string | null;
    city: string | null;
    address: string | null;
    description: string | null;
    founded_year: number | null;
    employees_range: string | null;
    verification_level: number;
    logo: string | null;
    cover: string | null;
};

type Contact = {
    type: string;
    label: string | null;
    contact_person: string | null;
    value: string;
    href: string | null;
};

/** Товар сайта: заведённый на самом сайте или объявление компании. */
type SiteProduct = {
    key: string;
    title: string;
    excerpt: string;
    cover: string | null;
    price: number | null;
    currency: string;
    unit: string | null;
    negotiable: boolean;
    category: string | null;
    /** Объявление ведёт на площадку; у товара сайта ссылки нет */
    url: string | null;
};

type SiteFile = {
    id: number;
    title: string;
    is_image: boolean;
    type_label: string;
    size: string;
    url: string;
};

type Reviews = {
    rating: number;
    count: number;
    latest: { id: number; author: string; rating: number; body: string; when: string }[];
};

type Props = {
    theme: SiteTheme;
    vars: Record<string, string>;
    fonts: string;
    /** Адрес фона первого экрана; null — фона нет */
    hero: string | null;
    preview: boolean;
    site: { url: string; marketplace: string };
    company: Company;
    initials: string;
    contacts: Contact[];
    products: SiteProduct[];
    files: SiteFile[];
    reviews: Reviews;
};

const CONTACT_ICONS: Record<string, typeof Phone> = {
    phone: Phone,
    email: Mail,
    telegram: Send,
    whatsapp: Send,
    website: Globe,
};

export default function SiteShow(props: Props) {
    const { theme, vars, fonts, preview, company, products, files, reviews, contacts } = props;

    usePreviewBridge(preview);

    // Шрифты меняются вместе с темой: при первой загрузке ссылку
    // печатает сервер, а в предпросмотре её подменяет эта страница
    useEffect(() => {
        const link = document.getElementById('ms-fonts');

        if (link instanceof HTMLLinkElement && link.href !== fonts) link.href = fonts;
    }, [fonts]);

    // Меню — три раздела, которые нужны покупателю: кто это, что
    // продают и как связаться. Документы и отзывы остаются на
    // странице ниже, но в меню их нет, чтобы оно не разрасталось
    const sections = [
        { id: 'about', label: t('site.nav.about') },
        { id: 'products', label: t('site.nav.products') },
        { id: 'contacts', label: t('site.nav.contacts') },
    ];

    return (
        <div className={`ms-root ms-tpl-${theme.template} ms-mode-${theme.mode}`} style={vars as CSSProperties}>
            <header className="ms-header">
                <div className="ms-container ms-header-row">
                    <a href="#top" className="ms-brand">
                        <Logo company={company} initials={props.initials} />
                        <span className="ms-brand-name">{company.name}</span>
                    </a>
                    <nav className="ms-nav" aria-label={t('site.nav.label')}>
                        {sections.map((s) => (
                            <a key={s.id} href={`#${s.id}`}>
                                {s.label}
                            </a>
                        ))}
                    </nav>
                    <a href="#contacts" className="ms-btn ms-btn-primary ms-btn-sm">
                        {t('site.contact_us')}
                    </a>
                </div>
            </header>

            <main id="top">
                <Hero {...props} />

                <Section id="about" title={t('site.about.title')}>
                    <div className="ms-about">
                        <div className="ms-prose">
                            {company.description ? (
                                company.description.split(/\n{2,}/).map((p, i) => <p key={i}>{p}</p>)
                            ) : (
                                <p className="ms-muted">{t('site.about.empty')}</p>
                            )}
                        </div>
                        <Facts company={company} />
                    </div>
                </Section>

                <Section id="products" title={t('site.products.title')} tinted>
                    {products.length > 0 ? (
                        <div className="ms-grid">
                            {products.map((p) => (
                                <ProductTile key={p.key} product={p} />
                            ))}
                        </div>
                    ) : (
                        <p className="ms-muted">{t('site.products.empty')}</p>
                    )}
                </Section>

                {files.length > 0 && (
                    <Section id="documents" title={t('site.documents.title')}>
                        <Documents files={files} />
                    </Section>
                )}

                {reviews.latest.length > 0 && (
                    <Section id="reviews" title={t('site.reviews.title')} tinted>
                        <p className="ms-rating">
                            <Star aria-hidden className="size-5" fill="currentColor" />
                            <b>{formatDecimal(reviews.rating)}</b>
                            <span className="ms-muted">{tChoice('site.reviews.count', reviews.count)}</span>
                        </p>
                        <div className="ms-grid ms-grid-wide">
                            {reviews.latest.map((r) => (
                                <figure key={r.id} className="ms-card ms-review">
                                    <p className="ms-stars" aria-label={t('site.reviews.stars', { rating: r.rating })}>
                                        {'★'.repeat(r.rating)}
                                        <span className="ms-stars-off">{'★'.repeat(5 - r.rating)}</span>
                                    </p>
                                    <blockquote>{r.body}</blockquote>
                                    <figcaption className="ms-muted">
                                        {r.author} · {r.when}
                                    </figcaption>
                                </figure>
                            ))}
                        </div>
                    </Section>
                )}

                <Section id="contacts" title={t('site.contacts.title')}>
                    <Contacts contacts={contacts} company={company} />
                </Section>
            </main>

            <footer className="ms-footer">
                <div className="ms-container ms-footer-row">
                    <span>
                        © {new Date().getFullYear()} {company.legal_name || company.name}
                    </span>
                    {/* Отметка площадки — единственное, что от неё здесь
                        видно. Ведёт на карточку компании: там отзывы и
                        проверка, которым покупатель доверяет больше, чем
                        сайту, сделанному самой компанией */}
                    <a href={props.site.marketplace} target="_blank" rel="noopener" className="ms-made">
                        {t('site.made_with')} <b>SAVDEX</b>
                    </a>
                </div>
            </footer>
        </div>
    );
}

/**
 * Связь с редактором: принимает оформление из родительского окна
 * и перерисовывает страницу. Только в предпросмотре и только от своего
 * окна того же адреса — иначе чужая страница, открывшая мини-сайт
 * во фрейме, могла бы его перекрашивать.
 */
function usePreviewBridge(preview: boolean) {
    const timer = useRef<number | undefined>(undefined);

    useEffect(() => {
        if (!preview) return;

        const onMessage = (event: MessageEvent) => {
            if (event.origin !== window.location.origin || event.source !== window.parent) return;

            const data = event.data as { type?: string; theme?: SiteTheme };

            if (data?.type !== THEME_MESSAGE || !data.theme) return;

            window.clearTimeout(timer.current);
            // Ползунок цвета шлёт десятки событий в секунду — на сервер
            // уходит только последнее
            timer.current = window.setTimeout(() => {
                router.reload({
                    data: { theme: JSON.stringify(data.theme) },
                    only: ['theme', 'vars', 'fonts', 'hero'],
                });
            }, 200);
        };

        window.addEventListener('message', onMessage);

        return () => {
            window.removeEventListener('message', onMessage);
            window.clearTimeout(timer.current);
        };
    }, [preview]);
}

function Logo({ company, initials }: { company: Company; initials: string }) {
    return company.logo ? (
        <img src={company.logo} alt="" className="ms-logo" />
    ) : (
        <span className="ms-logo ms-logo-initials" aria-hidden>
            {initials}
        </span>
    );
}

function Hero({ theme, company, initials, products, hero }: Props) {
    const subtitle = [company.custom_category || company.type_label, company.city || company.country]
        .filter(Boolean)
        .join(' · ');

    const lead = company.description?.split(/\n/)[0] ?? '';

    // Загруженный фон — в любом шаблоне. Без него классический шаблон
    // берёт обложку компании, остальные обходятся без картинки
    const photo = hero ?? (theme.template === 'classic' ? company.cover : null);

    return (
        <section
            className={photo ? 'ms-hero ms-hero-photo' : 'ms-hero'}
            style={photo ? { backgroundImage: `url("${photo}")` } : undefined}
        >
            <div className="ms-container ms-hero-inner">
                {theme.template !== 'minimal' && <Logo company={company} initials={initials} />}
                <h1 className="ms-hero-title">{company.name}</h1>
                {subtitle !== '' && <p className="ms-hero-sub">{subtitle}</p>}
                {lead !== '' && <p className="ms-hero-lead">{lead}</p>}
                <div className="ms-hero-actions">
                    <a href="#contacts" className="ms-btn ms-btn-accent ms-btn-cta">
                        {t('site.contact_us')}
                    </a>
                    {products.length > 0 && (
                        <a href="#products" className="ms-btn ms-btn-ghost">
                            {t('site.products.cta')}
                        </a>
                    )}
                </div>
            </div>
        </section>
    );
}

function Section({ id, title, tinted, children }: { id: string; title: string; tinted?: boolean; children: ReactNode }) {
    return (
        <section id={id} className={tinted ? 'ms-section ms-section-tinted' : 'ms-section'}>
            <div className="ms-container">
                <h2 className="ms-h2">{title}</h2>
                {children}
            </div>
        </section>
    );
}

function Facts({ company }: { company: Company }) {
    const facts: [string, string][] = [];

    if (company.founded_year) facts.push([t('site.about.founded'), String(company.founded_year)]);
    if (company.employees_range) facts.push([t('site.about.employees'), company.employees_range]);
    if (company.city || company.country)
        facts.push([t('site.about.location'), [company.city, company.country].filter(Boolean).join(', ')]);
    if (company.type_label) facts.push([t('site.about.type'), company.type_label]);

    return (
        <aside className="ms-card ms-facts">
            {company.verification_level > 0 && (
                <p className="ms-verified">
                    <BadgeCheck aria-hidden className="size-5" />
                    {t('site.about.verified')}
                </p>
            )}
            <dl>
                {facts.map(([label, value]) => (
                    <div key={label}>
                        <dt className="ms-muted">{label}</dt>
                        <dd>{value}</dd>
                    </div>
                ))}
            </dl>
        </aside>
    );
}

function ProductTile({ product: p }: { product: SiteProduct }) {
    const unit = unitLabel(p.unit);
    const price =
        p.negotiable || p.price === null
            ? t('site.products.negotiable')
            : money(p.price, p.currency) + (unit ? ` / ${unit}` : '');

    const body = (
        <>
            <div className="ms-tile-cover">
                {p.cover ? <img src={p.cover} alt="" loading="lazy" /> : <Package aria-hidden className="size-8" />}
            </div>
            <div className="ms-tile-body">
                {p.category && <p className="ms-tile-cat">{p.category}</p>}
                <h3 className="ms-tile-title">{p.title}</h3>
                {!p.url && p.excerpt !== '' && <p className="ms-tile-excerpt">{p.excerpt}</p>}
                <p className="ms-tile-price">{price}</p>
            </div>
        </>
    );

    return p.url ? (
        <a href={p.url} target="_blank" rel="noopener" className="ms-card ms-tile">
            {body}
        </a>
    ) : (
        <div className="ms-card ms-tile">{body}</div>
    );
}

function Documents({ files }: { files: SiteFile[] }) {
    const images = files.filter((f) => f.is_image);
    const docs = files.filter((f) => !f.is_image);

    return (
        <>
            {images.length > 0 && (
                <div className="ms-gallery">
                    {images.map((f) => (
                        <a key={f.id} href={f.url} target="_blank" rel="noopener" className="ms-gallery-item">
                            <img src={f.url} alt={f.title} loading="lazy" />
                        </a>
                    ))}
                </div>
            )}
            {docs.length > 0 && (
                <ul className="ms-docs">
                    {docs.map((f) => (
                        <li key={f.id}>
                            <a href={f.url} className="ms-card ms-doc">
                                <FileText aria-hidden className="size-5 shrink-0" />
                                <span className="ms-doc-title">
                                    {f.title}
                                    <small className="ms-muted">
                                        {f.type_label} · {f.size}
                                    </small>
                                </span>
                                <Download aria-hidden className="size-4 shrink-0" />
                            </a>
                        </li>
                    ))}
                </ul>
            )}
        </>
    );
}

function Contacts({ contacts, company }: { contacts: Contact[]; company: Company }) {
    const address = [company.address, company.city, company.country].filter(Boolean).join(', ');

    return (
        <div className="ms-contacts">
            {contacts.map((c, i) => {
                const Icon = CONTACT_ICONS[c.type] ?? Globe;
                const external = c.type === 'website' || c.type === 'telegram' || c.type === 'whatsapp';

                return (
                    <a
                        key={i}
                        href={c.href ?? undefined}
                        target={external ? '_blank' : undefined}
                        rel={external ? 'noopener' : undefined}
                        className="ms-card ms-contact"
                    >
                        <span className="ms-contact-icon">
                            <Icon aria-hidden className="size-5" />
                        </span>
                        <span className="min-w-0">
                            <small className="ms-muted">
                                {c.label || t(`site.contacts.types.${c.type}`)}
                                {c.contact_person ? ` · ${c.contact_person}` : ''}
                            </small>
                            <b className="ms-contact-value">{c.value}</b>
                        </span>
                    </a>
                );
            })}

            {address !== '' && (
                <a
                    href={`https://yandex.uz/maps/?text=${encodeURIComponent(address)}`}
                    target="_blank"
                    rel="noopener"
                    className="ms-card ms-contact"
                >
                    <span className="ms-contact-icon">
                        <MapPin aria-hidden className="size-5" />
                    </span>
                    <span className="min-w-0">
                        <small className="ms-muted">{t('site.contacts.address')}</small>
                        <b className="ms-contact-value">
                            {address} <ExternalLink aria-hidden className="inline size-3.5" />
                        </b>
                    </span>
                </a>
            )}

            {contacts.length === 0 && address === '' && <p className="ms-muted">{t('site.contacts.empty')}</p>}
        </div>
    );
}
