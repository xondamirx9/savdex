import { Head } from '@inertiajs/react';
import type { ReactNode } from 'react';
import { useEffect, useState } from 'react';
import { MobileTabBar } from '@/components/MobileTabBar';
import { SiteFooter } from '@/components/SiteFooter';
import { SiteHeader } from '@/components/SiteHeader';
import { cn } from '@/lib/cn';
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

    /*
     * Прокручена ли страница дальше шапки.
     *
     * Над первым экраном шапка прозрачная — сквозь неё видно кадр.
     * Ниже под ней идёт белая страница, и прозрачная шапка на ней
     * читается как набор слов, висящих поверх текста: нужен фон.
     *
     * Порог — высота самой шапки: к этому моменту кадр под ней
     * кончился. Значение публикует сама шапка в --hd-h.
     */
    const [scrolled, setScrolled] = useState(false);

    useEffect(() => {
        if (!overlayHeader) return;

        const onScroll = () => {
            const height = parseInt(
                getComputedStyle(document.documentElement).getPropertyValue('--hd-h'),
                10,
            );

            setScrolled(window.scrollY > (Number.isFinite(height) ? height : 120));
        };

        onScroll();
        window.addEventListener('scroll', onScroll, { passive: true });

        return () => window.removeEventListener('scroll', onScroll);
    }, [overlayHeader]);

    return (
        <>
            <Head title={title}>
                {description && <meta name="description" content={description} />}
            </Head>

            <a href="#main" className="skip-link">
                {t('common.skip_to_content')}
            </a>

            {/* Обёртка выводит шапку из потока и кладёт поверх первого
                экрана: фон страницы (фотография) виден сквозь неё.
                Шапка при этом остаётся на месте при прокрутке — на
                остальных страницах она прилипает сама (.hd — sticky),
                и первый экран не должен быть исключением. */}
            {overlayHeader ? (
                <div className={cn('chrome-overlay', scrolled && 'is-solid')}>
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
