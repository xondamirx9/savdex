import { Head, usePage } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import {
    BarChart3,
    Building2,
    CreditCard,
    Eye,
    LayoutDashboard,
    MailWarning,
    TriangleAlert,
    MessageSquareText,
    Package,
    Plus,
    Rocket,
    Settings,
    Star,
    Users,
} from 'lucide-react';
import type { ComponentType, ReactNode } from 'react';
import { Alert } from '@/components/ui';
import { MobileTabBar } from '@/components/MobileTabBar';
import { SiteHeader } from '@/components/SiteHeader';
import { routes } from '@/routes';
import type { CabinetCounts, SharedProps } from '@/types';

type Icon = ComponentType<{ className?: string; 'aria-hidden'?: boolean }>;

interface NavItem {
    href: string;
    label: string;
    icon: Icon;
    /** Ключ счётчика из props.counts — цифра рядом с пунктом */
    count?: keyof CabinetCounts;
}

interface NavGroup {
    title?: string;
    items: NavItem[];
}

const GROUPS: NavGroup[] = [
    {
        items: [
            { href: routes.cabinet, label: 'Дашборд', icon: LayoutDashboard },
            { href: routes.cabinetListings, label: 'Мои объявления', icon: Package, count: 'listings' },
            { href: routes.listingCreate, label: 'Создать объявление', icon: Plus },
        ],
    },
    {
        title: 'Контакты',
        items: [
            { href: routes.cabinetChats, label: 'Чаты', icon: MessageSquareText, count: 'chats' },
            { href: routes.cabinetContacts, label: 'Мои контакты', icon: Users, count: 'contacts' },
            { href: routes.cabinetIncoming, label: 'Кто мной интересуется', icon: Eye, count: 'incoming' },
        ],
    },
    {
        title: 'Рост',
        items: [
            { href: routes.cabinetAnalytics, label: 'Аналитика', icon: BarChart3 },
            { href: routes.cabinetPromo, label: 'Продвижение', icon: Rocket },
            { href: routes.cabinetReviews, label: 'Отзывы', icon: Star, count: 'reviews' },
        ],
    },
    {
        title: 'Аккаунт',
        items: [
            { href: routes.cabinetCompany, label: 'Компания', icon: Building2 },
            { href: routes.cabinetBilling, label: 'Тариф и оплата', icon: CreditCard },
            { href: routes.cabinetSettings, label: 'Настройки', icon: Settings },
        ],
    },
];

/**
 * Раскладка кабинета: шапка сайта, боковое меню разделов, содержимое.
 *
 * Шапка здесь обязательна. Без неё кабинет оказывался тупиком: ни выхода,
 * ни возврата на сайт, ни переключения языка — только адресная строка.
 */
export function CabinetLayout({
    title,
    heading,
    subheading,
    actions,
    children,
}: {
    title: string;
    heading: string;
    subheading?: ReactNode;
    actions?: ReactNode;
    children: ReactNode;
}) {
    const { auth, flash, counts } = usePage<SharedProps>().props;
    const path = typeof window !== 'undefined' ? window.location.pathname : routes.cabinet;
    const unverified = auth?.user && !auth.user.email_verified;

    const isActive = (href: string) => (href === routes.cabinet ? path === href : path.startsWith(href));

    return (
        <>
            <Head title={title} />
            <a href="#main" className="skip-link">
                Перейти к содержимому
            </a>

            <SiteHeader />

            {/* На телефоне боковое меню скрыто, а нижняя панель вмещает
                пять пунктов из двенадцати. Прокручиваемая полоса даёт
                доступ к остальным без ухода со страницы */}
            <nav className="side-scroll" aria-label="Разделы кабинета">
                <div className="container side-scroll-inner">
                    {GROUPS.flatMap((g) => g.items).map(({ href, label, icon: Icon, count }) => (
                        <Link key={href} href={href} aria-current={isActive(href) ? 'page' : undefined}>
                            <Icon aria-hidden className="size-4 shrink-0" />
                            {label}
                            {count && counts?.[count] ? <span className="side-count">{counts[count]}</span> : null}
                        </Link>
                    ))}
                </div>
            </nav>

            <div className="container">
                <div className="cabinet">
                    <nav className="side" aria-label="Разделы кабинета">
                        {GROUPS.map((group, gi) => (
                            <div key={group.title ?? gi} className="side-group">
                                {group.title && <div className="side-title">{group.title}</div>}
                                {group.items.map(({ href, label, icon: Icon, count }) => (
                                    <Link key={href} href={href} aria-current={isActive(href) ? 'page' : undefined}>
                                        <Icon aria-hidden className="size-5 shrink-0" />
                                        <span className="min-w-0 flex-1">{label}</span>
                                        {count && counts?.[count] ? (
                                            <span className="side-count">{counts[count]}</span>
                                        ) : null}
                                    </Link>
                                ))}
                            </div>
                        ))}
                    </nav>

                    <main id="main" className="min-w-0">
                            {flash?.success && (
                                <Alert tone="success" className="mb-5">
                                    {flash.success}
                                </Alert>
                            )}
                            {flash?.error && (
                                <Alert tone="danger" className="mb-5">
                                    {flash.error}
                                </Alert>
                            )}

                            {/* Заблокированная компания невидима на витрине,
                                хотя объявления в кабинете значатся активными.
                                Молчать об этом — заставлять владельца искать
                                поломку вместо причины */}
                            {auth?.company?.blocked && (
                                <div className="alert alert-danger" style={{ marginBottom: 20, alignItems: 'center' }}>
                                    <TriangleAlert aria-hidden className="size-5 shrink-0" />
                                    <div style={{ flex: 1, minWidth: 220 }}>
                                        <b>Компания заблокирована модератором</b> — визитка и объявления скрыты
                                        с витрины.
                                        {auth.company.blocked_reason && (
                                            <>
                                                {' '}
                                                Причина: {auth.company.blocked_reason}.
                                            </>
                                        )}{' '}
                                        Напишите в поддержку, чтобы восстановить доступ.
                                    </div>
                                </div>
                            )}

                            {/* Молчать о неподтверждённой почте нельзя: человек
                                упрётся в отказ на публикации и не поймёт причину */}
                            {unverified && (
                                <div className="alert alert-warning" style={{ marginBottom: 20, alignItems: 'center' }}>
                                    <MailWarning aria-hidden className="size-5 shrink-0" />
                                    <div className="row-between wrap" style={{ gap: 12, flex: 1 }}>
                                        <span style={{ flex: 1, minWidth: 220 }}>
                                            Почта <b className="break-all">{auth.user?.email}</b> не подтверждена.
                                            Публикация объявлений и раскрытие контактов пока недоступны.
                                        </span>
                                        <Link href={routes.verifyNotice} className="btn btn-secondary btn-sm shrink-0">
                                            Подтвердить
                                        </Link>
                                    </div>
                                </div>
                            )}

                            <div className="page-head">
                                <div className="min-w-0">
                                    <h1 className="t-h1">{heading}</h1>
                                    {subheading && <p className="t-lead mt-8">{subheading}</p>}
                                </div>
                                {actions && <div className="row wrap shrink-0" style={{ gap: 10 }}>{actions}</div>}
                            </div>

                        {children}
                    </main>
                </div>
            </div>

            <MobileTabBar />
        </>
    );
}
