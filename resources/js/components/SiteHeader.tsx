import { router, usePage } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import {
    AlertTriangle,
    Building2,
    ChevronDown,
    Globe,
    Heart,
    LayoutDashboard,
    LogOut,
    Megaphone,
    Menu,
    MessageSquareText,
    PlusCircle,
    Search,
    Settings,
    Shield,
    Wallet,
    X,
} from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { cn } from '@/lib/cn';
import { stripLocale } from '@/lib/locale';
import { t, tChoice } from '@/lib/i18n';
import { routes } from '@/routes';
import type { SharedProps } from '@/types';

/**
 * Шапка сайта — один компонент на все страницы.
 *
 * Три яруса, как в макете новой витрины: жёлтая полоса тестового
 * режима, основная строка с логотипом, поиском и действиями,
 * и лента разделов. Состав задан один раз — рассинхрон невозможен.
 */

interface MenuItem {
    href: string;
    label: string;
    /** Пункт с query-строкой активен только при точном совпадении её части. */
    match?: (path: string, search: string) => boolean;
}

/**
 * Лента разделов.
 *
 * Собирается функцией, а не константой модуля: подписи берутся из
 * словаря, а он приходит с сервером. Константа вычислилась бы один
 * раз при загрузке файла — до того, как словарь установлен.
 *
 * «Запросы (RFQ)» — каталог с фильтром по типу «спрос»: запрос
 * на закупку и есть RFQ, отдельной сущности для него не нужно.
 */
function menu(): MenuItem[] {
    const rfq = `${routes.catalog}?type=demand`;

    return [
        { href: routes.companies, label: t('nav.companies') },
        {
            href: routes.catalog,
            label: t('nav.products'),
            match: (path, search) => path.startsWith(routes.catalog) && !search.includes('type=demand'),
        },
        {
            href: rfq,
            label: t('nav.rfq'),
            match: (path, search) => path.startsWith(routes.catalog) && search.includes('type=demand'),
        },
        { href: routes.countries, label: t('nav.countries') },
        { href: routes.news, label: t('nav.news') },
        { href: routes.about, label: t('nav.about_us') },
        { href: routes.contacts, label: t('nav.contacts') },
    ];
}

/** Закрывает выпадающий блок при клике снаружи и по Escape. */
function useDismiss(onDismiss: () => void) {
    const ref = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const onClick = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) onDismiss();
        };
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onDismiss();
        };
        document.addEventListener('click', onClick);
        document.addEventListener('keydown', onKey);
        return () => {
            document.removeEventListener('click', onClick);
            document.removeEventListener('keydown', onKey);
        };
    }, [onDismiss]);

    return ref;
}

/**
 * Полоса тестового режима.
 *
 * Закрывается крестиком и запоминает это в localStorage: полоса —
 * предупреждение, а не украшение, и показывать её человеку, который
 * уже прочитал и закрыл, значит приучать не читать предупреждения.
 */
const TOPBAR_KEY = 'savdex.topbar.closed';

function TopBar() {
    const [closed, setClosed] = useState(true);

    // Начальное состояние читается в эффекте: при SSR localStorage нет,
    // и чтение в useState уронило бы отрисовку на сервере
    useEffect(() => {
        setClosed(localStorage.getItem(TOPBAR_KEY) === '1');
    }, []);

    if (closed) return null;

    return (
        <div className="topbar" role="status">
            <div className="container topbar-inner">
                <div className="topbar-text">
                    <b>
                        <AlertTriangle aria-hidden className="size-4" />
                        {t('topbar.title')}
                    </b>
                    <span className="topbar-note">{t('topbar.text')}</span>
                </div>
                <div className="topbar-actions">
                    <Link href={routes.about} className="topbar-more">
                        {t('topbar.more')}
                    </Link>
                    <button
                        className="topbar-close"
                        aria-label={t('topbar.close')}
                        onClick={() => {
                            localStorage.setItem(TOPBAR_KEY, '1');
                            setClosed(true);
                        }}
                    >
                        <X aria-hidden className="size-4" />
                    </button>
                </div>
            </div>
        </div>
    );
}

/**
 * Переключатель языка.
 *
 * Обычные ссылки на ту же страницу с другим префиксом, а не кнопки:
 * такую ссылку видит поисковик, её можно скопировать и открыть в
 * соседней вкладке. Переход намеренно полный, без Inertia: вместе
 * со страницей должен приехать словарь нового языка.
 */
function LangSwitcher({ locale, links }: { locale: string; links: SharedProps['localeLinks'] }) {
    const [open, setOpen] = useState(false);
    const ref = useDismiss(() => setOpen(false));
    const current = links.find((l) => l.code === locale) ?? links[0];

    // Страница ошибки может прийти без общих пропсов — переключателю
    // без списка языков нечего показывать, и падать из-за этого нельзя
    if (!current) return null;

    return (
        <div className="dropdown lang-switch" ref={ref}>
            <button
                className="btn btn-ghost btn-sm"
                aria-expanded={open}
                aria-haspopup="true"
                aria-label={`${t('nav.language')}: ${current.label}`}
                onClick={(e) => {
                    e.stopPropagation();
                    setOpen((v) => !v);
                }}
            >
                <Globe aria-hidden className="size-4" />
                {current.short}
                <ChevronDown aria-hidden className="size-3.5" />
            </button>
            <div className={cn('dropdown-menu', open && 'open')} aria-label={t('nav.language')}>
                {links.map((l) => (
                    <a
                        key={l.code}
                        href={l.url}
                        className="dropdown-item"
                        hrefLang={l.code}
                        aria-current={l.code === current.code ? 'true' : undefined}
                    >
                        {l.label}
                    </a>
                ))}
            </div>
        </div>
    );
}

/**
 * Поиск в шапке: запрос + раздел каталога + кнопка.
 *
 * Отправляет в каталог обычным GET через Inertia — тот же адрес
 * можно скопировать из строки браузера и переслать.
 */
function HeaderSearch({
    categories,
    idPrefix,
}: {
    categories: NonNullable<SharedProps['navCategories']>;
    /** Форма рендерится дважды (десктоп и телефон) — id обязаны различаться. */
    idPrefix: string;
}) {
    const [q, setQ] = useState('');
    const [category, setCategory] = useState('');

    function submit(e: React.FormEvent) {
        e.preventDefault();

        const params: Record<string, string | number> = {};
        if (q.trim() !== '') params.q = q.trim();
        if (category !== '') params.category = Number(category);

        router.get(routes.catalog, params);
    }

    return (
        <form className="hd-search" role="search" onSubmit={submit}>
            <label htmlFor={`${idPrefix}-q`} className="sr-only">
                {t('header.search_label')}
            </label>
            <input
                id={`${idPrefix}-q`}
                type="search"
                placeholder={t('header.search_placeholder')}
                value={q}
                onChange={(e) => setQ(e.target.value)}
            />
            <label htmlFor={`${idPrefix}-cat`} className="sr-only">
                {t('catalog.category')}
            </label>
            <select id={`${idPrefix}-cat`} value={category} onChange={(e) => setCategory(e.target.value)}>
                <option value="">{t('header.all_categories')}</option>
                {categories.map((c) => (
                    <option key={c.id} value={c.id}>
                        {c.name}
                    </option>
                ))}
            </select>
            <button type="submit">
                <Search aria-hidden className="size-4" />
                <span className="hide-mobile">{t('header.search_button')}</span>
            </button>
        </form>
    );
}

/**
 * Сколько контактов можно открыть прямо сейчас.
 *
 * Одна цифра, а не «кредиты»: расходуется сначала месячный лимит
 * тарифа и лишь потом купленные кредиты, поэтому человека интересует
 * сумма — «сколько я могу открыть». Раскладка вынесена в подсказку.
 */
function ContactsLeft({ wallet }: { wallet: SharedProps['contactsLeft'] }) {
    if (!wallet) return null;

    const unlimited = wallet.total === null;
    const empty = !unlimited && wallet.total === 0;

    const hint = unlimited
        ? t('header.unlimited')
        : [
              wallet.resets_at
                  ? t('header.plan_left_until', { count: wallet.plan_left ?? 0, date: wallet.resets_at })
                  : t('header.plan_left', { count: wallet.plan_left ?? 0 }),
              t('header.credits_bought', { count: wallet.credits }),
          ].join(' + ');

    return (
        <Link
            href={routes.cabinetBilling}
            className="hd-action hd-action--wallet"
            title={t('header.contacts_title', { hint })}
        >
            <Wallet aria-hidden />
            {!unlimited && (
                <span className={cn('hd-badge', empty && 'hd-badge--zero')}>{wallet.total}</span>
            )}
            <span>
                {empty
                    ? t('header.topup')
                    : unlimited
                      ? t('header.contacts_word')
                      : tChoice('header.contacts_choice', wallet.total ?? 0)}
            </span>
        </Link>
    );
}

/**
 * Сообщения площадки — колокольчик в облике мессенджера.
 *
 * Показывает пять последних и число непрочитанных. Полный список —
 * отдельной страницей: выпадающий блок на сорок записей превращается
 * в собственную страницу внутри шапки.
 */
function MessagesMenu({ data }: { data: NonNullable<SharedProps['bell']> }) {
    const [open, setOpen] = useState(false);
    const ref = useDismiss(() => setOpen(false));

    return (
        <div className="dropdown" ref={ref} data-dropdown-keep>
            <button
                className="hd-action"
                aria-label={
                    data.unread > 0
                        ? t('header.notifications_unread', { count: data.unread })
                        : t('header.messages')
                }
                aria-expanded={open}
                onClick={(e) => {
                    e.stopPropagation();
                    setOpen((v) => !v);
                }}
            >
                <MessageSquareText aria-hidden />
                {data.unread > 0 && <span className="hd-badge">{data.unread > 99 ? '99+' : data.unread}</span>}
                <span>{t('header.messages')}</span>
            </button>

            <div className={cn('dropdown-menu dropdown-menu-wide', open && 'open')} role="menu">
                <div className="dropdown-head row-between">
                    <b>{t('header.notifications')}</b>
                    {data.unread > 0 && (
                        <button
                            className="t-caption"
                            onClick={() => {
                                setOpen(false);
                                router.post(routes.notificationsReadAll, {}, { preserveScroll: true });
                            }}
                        >
                            {t('header.mark_all')}
                        </button>
                    )}
                </div>

                {data.latest.length === 0 ? (
                    <p className="t-sm muted" style={{ padding: '12px 12px 14px' }}>
                        {t('header.notifications_empty')}
                    </p>
                ) : (
                    data.latest.map((n) => (
                        <Link
                            key={n.id}
                            href={routes.notificationRead(n.id)}
                            method="post"
                            as="button"
                            className={cn('dropdown-item notif-item', !n.read && 'is-unread')}
                            role="menuitem"
                            onClick={() => setOpen(false)}
                        >
                            <span className={cn('notif-mark', `tone-${n.tone}`)} aria-hidden />
                            <span style={{ minWidth: 0 }}>
                                <span className="notif-title">{n.title}</span>
                                <span className="t-caption muted">{n.ago}</span>
                            </span>
                        </Link>
                    ))
                )}

                <Link href={routes.notifications} className="dropdown-item dropdown-all" onClick={() => setOpen(false)}>
                    {t('header.notifications_all')}
                </Link>
            </div>
        </div>
    );
}

/**
 * Меню вошедшего пользователя.
 *
 * Появилось после того, как выяснилось, что выйти из аккаунта было
 * невозможно ни с одной страницы: кнопки выхода не существовало нигде.
 */
function UserMenu({ name, email, verified, isAdmin }: { name: string; email: string; verified: boolean; isAdmin: boolean }) {
    const [open, setOpen] = useState(false);
    const ref = useDismiss(() => setOpen(false));

    const short = name.split(' ')[0] || name;
    const initials = name
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((w) => w[0])
        .join('')
        .toUpperCase();

    return (
        <div className="dropdown user-menu" ref={ref}>
            <button
                className="user-menu-btn"
                aria-expanded={open}
                aria-haspopup="true"
                aria-label={t('header.user_menu', { name })}
                onClick={(e) => {
                    e.stopPropagation();
                    setOpen((v) => !v);
                }}
            >
                <span className="user-avatar" aria-hidden>
                    {initials || '?'}
                </span>
                <span className="hide-mobile">{short}</span>
                <ChevronDown aria-hidden className="size-4 hide-mobile" />
            </button>

            <div className={cn('dropdown-menu dropdown-menu-wide', open && 'open')} role="menu">
                <div className="dropdown-head">
                    <b>{name}</b>
                    <span className="t-caption muted">{email}</span>
                    {!verified && (
                        <span className="badge badge-warning" style={{ marginTop: 6, alignSelf: 'flex-start' }}>
                            {t('header.email_unverified')}
                        </span>
                    )}
                </div>

                {isAdmin && (
                    /* Обычная ссылка, а не Inertia: панель — отдельное
                       приложение, ей нужна полная загрузка страницы */
                    <a href="/admin" className="dropdown-item" role="menuitem">
                        <Shield aria-hidden className="size-4" /> {t('header.admin_panel')}
                    </a>
                )}
                <Link href={routes.cabinet} className="dropdown-item" role="menuitem" onClick={() => setOpen(false)}>
                    <LayoutDashboard aria-hidden className="size-4" /> {t('header.summary')}
                </Link>
                <Link
                    href={routes.cabinetListings}
                    className="dropdown-item"
                    role="menuitem"
                    onClick={() => setOpen(false)}
                >
                    <Megaphone aria-hidden className="size-4" /> {t('header.my_listings')}
                </Link>
                <Link
                    href={routes.cabinetCompany}
                    className="dropdown-item"
                    role="menuitem"
                    onClick={() => setOpen(false)}
                >
                    <Building2 aria-hidden className="size-4" /> {t('header.company')}
                </Link>
                <Link
                    href={routes.favorites}
                    className="dropdown-item"
                    role="menuitem"
                    onClick={() => setOpen(false)}
                >
                    <Heart aria-hidden className="size-4" /> {t('header.favorites')}
                </Link>
                <Link
                    href={routes.cabinetSettings}
                    className="dropdown-item"
                    role="menuitem"
                    onClick={() => setOpen(false)}
                >
                    <Settings aria-hidden className="size-4" /> {t('header.settings')}
                </Link>

                {/* Выход — POST, а не ссылка: GET-выход срабатывает от
                    предзагрузки браузером и от чужой картинки на странице */}
                <button
                    className="dropdown-item dropdown-item-danger"
                    role="menuitem"
                    onClick={() => {
                        setOpen(false);
                        router.post(routes.logout);
                    }}
                >
                    <LogOut aria-hidden className="size-4" /> {t('nav.logout')}
                </button>
            </div>
        </div>
    );
}

export function SiteHeader() {
    const props = usePage<SharedProps>().props as SharedProps & { url?: string };
    const { auth, bell, contactsLeft, favorites, navCategories, url } = props;
    /*
     * Страница ошибки (404, 419) рендерится без общих пропсов:
     * посредник Inertia не запускается, когда маршрут не совпал.
     * Каждый общий проп обязан переживать undefined — иначе вместо
     * задизайненной страницы ошибки будет белый экран.
     */
    const locale = props.locale ?? 'ru';
    const localeLinks = props.localeLinks ?? [];
    const items = menu();
    /*
     * Язык из адреса убирается: пути в routes.* записаны без него,
     * и на узбекской версии активный пункт меню не подсвечивался бы.
     */
    const path = stripLocale(typeof window !== 'undefined' ? window.location.pathname : (url ?? '/'));
    const search = typeof window !== 'undefined' ? window.location.search : '';
    const [menuOpen, setMenuOpen] = useState(false);
    const headerRef = useRef<HTMLElement>(null);
    /*
     * Верхний край мобильного меню — под нижним краем шапки.
     * Высота шапки плавает: полоса тестового режима закрывается,
     * строка поиска на телефоне добавляется, — поэтому измеряем,
     * а не зашиваем константу. Иначе меню открывалось бы под шапкой
     * и первый пункт был бы скрыт и некликабелен.
     */
    const [menuTop, setMenuTop] = useState<number | undefined>(undefined);

    const authed = Boolean(auth?.user);
    const favCount = (favorites ?? []).length;
    const categories = navCategories ?? [];

    const isActive = (item: MenuItem) =>
        item.match
            ? item.match(path, search)
            : path.startsWith(item.href.split('?')[0]) && item.href !== '/';

    // Прокрутка страницы под открытым меню сбивает с толку
    useEffect(() => {
        document.body.style.overflow = menuOpen ? 'hidden' : '';

        if (menuOpen && headerRef.current) {
            setMenuTop(Math.max(0, headerRef.current.getBoundingClientRect().bottom));
        }

        return () => {
            document.body.style.overflow = '';
        };
    }, [menuOpen]);

    return (
        <>
            <TopBar />

            <header className="hd" ref={headerRef}>
                <div className="container">
                    <div className="hd-main">
                        <Link href={routes.home} className="hd-logo" aria-label={t('nav.home_link')}>
                            <img src="/images/logo-mark.svg" alt="" aria-hidden className="logo-img" />
                            <span className="hd-logo-word">
                                <span className="hd-logo-name">
                                    Savd<span>Ex</span>
                                </span>
                                <span className="hd-logo-sub">{t('header.tagline')}</span>
                            </span>
                        </Link>

                        <HeaderSearch categories={categories} idPrefix="hd" />

                        <LangSwitcher locale={locale} links={localeLinks} />

                        <div className="hd-actions">
                            {/* Избранное — только вошедшим: гостю сердечко
                                ничего не даёт, кроме лишнего клика в /login */}
                            {authed && (
                                <Link href={routes.favorites} className="hd-action" aria-label={t('header.favorites')}>
                                    <Heart aria-hidden />
                                    {favCount > 0 && <span className="hd-badge">{favCount > 99 ? '99+' : favCount}</span>}
                                    <span>{t('header.favorites')}</span>
                                </Link>
                            )}

                            {/* Сообщения — тоже только вошедшим: гостю ссылка
                                вела в /login и ничего не сообщала */}
                            {authed && bell && <MessagesMenu data={bell} />}

                            {authed && <ContactsLeft wallet={contactsLeft} />}
                        </div>

                        {authed ? (
                            <UserMenu
                                name={auth.user!.name}
                                email={auth.user!.email}
                                verified={auth.user!.email_verified}
                                isAdmin={auth.user!.is_admin}
                            />
                        ) : (
                            <div className="hd-auth">
                                <Link href={routes.login} className="btn btn-secondary btn-sm nav-auth">
                                    {t('nav.login')}
                                </Link>
                                <Link href={routes.register} className="btn btn-primary btn-sm">
                                    {t('nav.register')}
                                </Link>
                            </div>
                        )}

                        <button
                            className="burger"
                            aria-label={menuOpen ? t('nav.close_menu') : t('nav.menu')}
                            aria-expanded={menuOpen}
                            aria-controls="mobile-menu"
                            onClick={() => setMenuOpen((v) => !v)}
                        >
                            {menuOpen ? <X aria-hidden className="size-6" /> : <Menu aria-hidden className="size-6" />}
                        </button>
                    </div>

                    {/* Поиск на телефоне — отдельной строкой под шапкой */}
                    <div className="hd-search-mobile">
                        <HeaderSearch categories={categories} idPrefix="hdm" />
                    </div>
                </div>

                <nav className="subnav" aria-label={t('nav.main')}>
                    <div className="container subnav-inner">
                        {items.map((item) => (
                            <Link key={item.href} href={item.href} aria-current={isActive(item) ? 'page' : undefined}>
                                {item.label}
                            </Link>
                        ))}
                        <Link href={authed ? routes.listingCreate : routes.register} className="subnav-post">
                            {t('nav.post_listing')} <PlusCircle aria-hidden />
                        </Link>
                    </div>
                </nav>
            </header>

            <nav
                className={cn('mobile-menu', menuOpen && 'open')}
                id="mobile-menu"
                aria-label={t('nav.mobile')}
                style={menuTop !== undefined ? { top: menuTop } : undefined}
            >
                <div className="mobile-menu-inner">
                    {items.map((item) => (
                        <Link key={item.href} href={item.href} onClick={() => setMenuOpen(false)}>
                            {item.label}
                        </Link>
                    ))}

                    <Link href={routes.pricing} onClick={() => setMenuOpen(false)}>
                        {t('nav.pricing')}
                    </Link>

                    {authed && (
                        <Link href={routes.favorites} onClick={() => setMenuOpen(false)}>
                            {t('header.favorites')}
                        </Link>
                    )}

                    <Link href={authed ? routes.cabinet : routes.login} onClick={() => setMenuOpen(false)}>
                        {authed ? t('nav.cabinet') : t('nav.login')}
                    </Link>

                    {!authed && (
                        <Link href={routes.register} onClick={() => setMenuOpen(false)}>
                            {t('nav.register')}
                        </Link>
                    )}

                    {authed && (
                        <button
                            className="mobile-logout"
                            onClick={() => {
                                setMenuOpen(false);
                                router.post(routes.logout);
                            }}
                        >
                            <LogOut aria-hidden className="size-5" /> {t('nav.logout')}
                        </button>
                    )}

                    <div className="mobile-menu-foot">
                        <Link
                            href={authed ? routes.listingCreate : routes.register}
                            className="btn btn-primary btn-lg btn-block"
                            onClick={() => setMenuOpen(false)}
                        >
                            {t('nav.post_listing')}
                        </Link>
                        <div className="mobile-lang">
                            <span className="t-sm muted">{t('nav.language_short')}</span>
                            {/* Ссылки, а не кнопки: язык — часть адреса,
                                и переход должен быть полным, чтобы вместе
                                со страницей приехал словарь нового языка */}
                            {localeLinks.map((l) => (
                                <a
                                    key={l.code}
                                    href={l.url}
                                    hrefLang={l.code}
                                    className={cn('chip', l.code === locale && 'chip-active')}
                                >
                                    {l.short}
                                </a>
                            ))}
                        </div>
                    </div>
                </div>
            </nav>
        </>
    );
}
