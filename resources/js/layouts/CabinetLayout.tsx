import { Head, usePage } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import {
    FileUser,
    BarChart3,
    Building2,
    Code2,
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
import { t } from '@/lib/i18n';

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

/**
 * Разделы кабинета.
 *
 * Функция, а не константа модуля: t() читает словарь, а словарь
 * приходит с сервера и ставится при запуске приложения. Значение,
 * посчитанное при импорте модуля, успевало взяться раньше словаря,
 * и в меню выходили сами ключи — «cabinet.nav.dashboard».
 */
function groups(): NavGroup[] {
    return [
        {
            items: [
                { href: routes.cabinet, label: t('cabinet.nav.dashboard'), icon: LayoutDashboard },
                { href: routes.cabinetListings, label: t('cabinet.nav.listings'), icon: Package, count: 'listings' },
                { href: routes.cabinetResume, label: t('cabinet.nav.resume'), icon: FileUser },
                { href: routes.listingCreate, label: t('cabinet.nav.create'), icon: Plus },
                { href: routes.cabinetItTasks, label: t('cabinet.nav.it_tasks'), icon: Code2 },
            ],
        },
        {
            title: t('cabinet.nav.contacts_group'),
            items: [
                { href: routes.cabinetChats, label: t('cabinet.nav.chats'), icon: MessageSquareText, count: 'chats' },
                { href: routes.cabinetContacts, label: t('cabinet.nav.contacts'), icon: Users, count: 'contacts' },
                { href: routes.cabinetIncoming, label: t('cabinet.nav.incoming'), icon: Eye, count: 'incoming' },
            ],
        },
        {
            title: t('cabinet.nav.growth_group'),
            items: [
                { href: routes.cabinetAnalytics, label: t('cabinet.nav.analytics'), icon: BarChart3 },
                { href: routes.cabinetPromo, label: t('cabinet.nav.promo'), icon: Rocket },
                { href: routes.cabinetReviews, label: t('cabinet.nav.reviews'), icon: Star, count: 'reviews' },
            ],
        },
        {
            title: t('cabinet.nav.account_group'),
            items: [
                { href: routes.cabinetCompany, label: t('cabinet.nav.company'), icon: Building2 },
                { href: routes.cabinetBilling, label: t('cabinet.nav.billing'), icon: CreditCard },
                { href: routes.cabinetSettings, label: t('cabinet.nav.settings'), icon: Settings },
            ],
        },
    ];
}

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
    const GROUPS = groups();
    const path = typeof window !== 'undefined' ? window.location.pathname : routes.cabinet;
    const unverified = auth?.user && !auth.user.email_verified;

    const isActive = (href: string) => (href === routes.cabinet ? path === href : path.startsWith(href));

    return (
        <>
            <Head title={title} />
            <a href="#main" className="skip-link">
                {t('common.skip_to_content')}
            </a>

            <SiteHeader />

            {/* На телефоне боковое меню скрыто, а нижняя панель вмещает
                пять пунктов из двенадцати. Прокручиваемая полоса даёт
                доступ к остальным без ухода со страницы */}
            <nav className="side-scroll" aria-label={t('cabinet.nav.sections')}>
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
                    <nav className="side" aria-label={t('cabinet.nav.sections')}>
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
                                        <b>{t('cabinet.blocked_title')}</b> {t('cabinet.blocked_text')}
                                        {auth.company.blocked_reason && (
                                            <>
                                                {' '}
                                                {t('cabinet.blocked_reason', { reason: auth.company.blocked_reason })}
                                            </>
                                        )}{' '}
                                        {t('cabinet.blocked_support')}
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
                                            {t('cabinet.unverified', { email: auth.user?.email ?? '' })}
                                        </span>
                                        <Link href={routes.verifyNotice} className="btn btn-secondary btn-sm shrink-0">
                                            {t('cabinet.verify')}
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
