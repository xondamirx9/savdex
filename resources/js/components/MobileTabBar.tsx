import { usePage } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { Heart, Home, LayoutDashboard, Package, Plus } from 'lucide-react';
import { t } from '@/lib/i18n';
import { stripLocale } from '@/lib/locale';
import { routes } from '@/routes';
import type { SharedProps } from '@/types';

/**
 * Нижняя навигация на телефоне.
 *
 * Показывается на всех страницах, а не только в кабинете: на узком
 * экране верхнее меню спрятано в бургер, и без нижней панели любое
 * перемещение по сайту начинается с двух нажатий.
 *
 * Пять пунктов — предел, при котором подписи ещё читаются на 320 px.
 */
const items = () => [
    { href: routes.home, label: t('tabbar.home'), icon: Home, exact: true },
    { href: routes.catalog, label: t('tabbar.listings'), icon: Package },
    { href: routes.listingCreate, label: t('tabbar.create'), icon: Plus },
    { href: routes.favorites, label: t('tabbar.favorites'), icon: Heart },
    { href: routes.cabinet, label: t('tabbar.cabinet'), icon: LayoutDashboard, exact: true },
];

export function MobileTabBar() {
    const { auth } = usePage<SharedProps>().props;
    /*
     * Язык из адреса убирается: пути в routes.* записаны без него,
     * и на узбекской версии ни один пункт не подсвечивался бы.
     */
    const path = stripLocale(typeof window !== 'undefined' ? window.location.pathname : '/');
    const authed = Boolean(auth?.user);

    const isActive = (href: string, exact?: boolean) => (exact ? path === href : path.startsWith(href));

    return (
        <nav className="tabbar" aria-label={t('nav.main')}>
            {items().map(({ href, label, icon: Icon, exact }) => (
                <Link
                    key={href}
                    // Гостя ведём на вход: страница всё равно потребует
                    // авторизации, а лишний редирект выглядит как сбой
                    href={authed || href === routes.home || href === routes.catalog ? href : routes.login}
                    aria-current={isActive(href, exact) ? 'page' : undefined}
                >
                    <Icon aria-hidden className="size-5" />
                    {label}
                </Link>
            ))}
        </nav>
    );
}
