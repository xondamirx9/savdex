import { t } from '@/lib/i18n';

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

export function DocsNav({ items, active, onAbout = false }: { items: DocsNavItem[]; active: string; onAbout?: boolean }) {
    return (
        <aside>
            <nav className="doc-nav card" style={{ padding: 10 }} aria-label={t('about.sections')}>
                {items.map((item) => (
                    <a
                        key={item.key}
                        href={onAbout ? localHref(item.href) : item.href}
                        aria-current={active === item.key ? 'true' : undefined}
                    >
                        {item.label}
                    </a>
                ))}
            </nav>
        </aside>
    );
}
