import { useEffect, useRef } from 'react';

import { t } from '@/lib/i18n';
import { localize } from '@/lib/locale';

export interface DocsNavItem {
    key: string;
    href: string;
    label: string;
}

/**
 * Оглавление страниц о площадке: «О компании» с контактами и офисом,
 * «Помощь», «Инструкция», «Правила». Пункты собирает сервер —
 * скрытая в админке страница в оглавление не попадает.
 *
 * Обычные ссылки, а не переходы Inertia: у «Контактов» и «Офиса»
 * якорь, и браузер сам докрутит до раздела.
 */
/** На самой странице «О компании» её пункты — якоря: прокрутка без перехода. */
function localHref(href: string): string {
    if (href === '/about') return '#about';

    return href.startsWith('/about#') ? href.slice('/about'.length) : href;
}

/**
 * Внутренний путь получает язык страницы: сервер отдаёт пути без
 * префикса, и на /uz/help ссылка «/rules» уводила бы на русскую
 * версию. Якоря и внешние адреса localize() не трогает, а хвост
 * «#contacts» переносит вместе с путём.
 */
function hrefFor(href: string, onAbout: boolean): string {
    return localize(onAbout ? localHref(href) : href);
}

export function DocsNav({ items, active, onAbout = false }: { items: DocsNavItem[]; active: string; onAbout?: boolean }) {
    const nav = useRef<HTMLElement>(null);

    /* На узком экране оглавление — лента с прокруткой вбок: активный
       пункт плавно подъезжает в видимую часть. Прокручиваем только
       саму ленту — scrollIntoView дёргал бы ещё и страницу */
    useEffect(() => {
        const strip = nav.current;
        const link = strip?.querySelector<HTMLElement>('a[aria-current="true"]');

        if (!strip || !link || strip.scrollWidth <= strip.clientWidth) return;

        // Положение пункта — от края ленты: у ленты нет position, и
        // offsetLeft считался бы от другого предка
        const box = link.getBoundingClientRect();
        const left = strip.scrollLeft + box.left - strip.getBoundingClientRect().left - (strip.clientWidth - box.width) / 2;
        const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

        strip.scrollTo({ left: Math.max(0, left), behavior: reduce ? 'auto' : 'smooth' });
    }, [active]);

    return (
        <aside>
            <nav ref={nav} className="doc-nav card" style={{ padding: 10 }} aria-label={t('about.sections')}>
                {items.map((item) => (
                    <a
                        key={item.key}
                        href={hrefFor(item.href, onAbout)}
                        aria-current={active === item.key ? 'true' : undefined}
                        data-label={item.label}
                    >
                        {item.label}
                    </a>
                ))}
            </nav>
        </aside>
    );
}
