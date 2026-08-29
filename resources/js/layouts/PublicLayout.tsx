import { Head } from '@inertiajs/react';
import type { ReactNode } from 'react';
import { MobileTabBar } from '@/components/MobileTabBar';
import { SiteFooter } from '@/components/SiteFooter';
import { SiteHeader } from '@/components/SiteHeader';
import { t } from '@/lib/i18n';
import { useReveal } from '@/lib/useReveal';

/**
 * Раскладка публичных страниц: шапка, содержимое, подвал.
 * Ссылка «перейти к содержимому» — первый элемент в потоке фокуса,
 * иначе клавиатурному пользователю приходится проходить всё меню.
 */
export function PublicLayout({
    title,
    description,
    children,
    noFooter = false,
    overlayHeader = false,
}: {
    title: string;
    description?: string;
    children: ReactNode;
    noFooter?: boolean;
    /** Прозрачная шапка поверх первого экрана — фотография фона просвечивает сквозь неё. */
    overlayHeader?: boolean;
}) {
    // Пересобираем наблюдатель при смене страницы: Inertia не перезагружает
    // документ, и новые блоки иначе остались бы невидимыми
    useReveal([title]);

    return (
        <>
            <Head title={title}>
                {description && <meta name="description" content={description} />}
            </Head>

            <a href="#main" className="skip-link">
                {t('common.skip_to_content')}
            </a>

            {/* Обёртка выводит шапку из потока и кладёт поверх первого
                экрана: фон страницы (фотография) виден сквозь неё */}
            {overlayHeader ? (
                <div className="chrome-overlay">
                    <SiteHeader />
                </div>
            ) : (
                <SiteHeader />
            )}
            <main id="main">{children}</main>
            {!noFooter && <SiteFooter />}
            <MobileTabBar />
        </>
    );
}
