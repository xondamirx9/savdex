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
    return (
        <aside>
            <nav className="doc-nav card" style={{ padding: 10 }} aria-label={t('about.sections')}>
                {items.map((item) => (
                    <a
                        key={item.key}
                        href={hrefFor(item.href, onAbout)}
                        aria-current={active === item.key ? 'true' : undefined}
                    >
                        {item.label}
                    </a>
                ))}
            </nav>
        </aside>
    );
}
