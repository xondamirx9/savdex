import { ChevronDown, Globe } from 'lucide-react';
import { useState } from 'react';
import { cn } from '@/lib/cn';
import { t } from '@/lib/i18n';
import { useDismiss } from '@/lib/useDismiss';
import type { SharedProps } from '@/types';

/**
 * Переключатель языка — в шапке сайта и на экранах входа и регистрации.
 *
 * Обычные ссылки на ту же страницу с другим префиксом, а не кнопки:
 * такую ссылку видит поисковик, её можно скопировать и открыть в
 * соседней вкладке. Переход намеренно полный, без Inertia: вместе
 * со страницей должен приехать словарь нового языка.
 */
export function LangSwitcher({
    locale,
    links,
    className,
}: {
    locale: string;
    links: SharedProps['localeLinks'];
    className?: string;
}) {
    const [open, setOpen] = useState(false);
    const ref = useDismiss(() => setOpen(false));
    const current = links.find((l) => l.code === locale) ?? links[0];

    // Страница ошибки может прийти без общих пропсов — переключателю
    // без списка языков нечего показывать, и падать из-за этого нельзя
    if (!current) return null;

    return (
        <div className={cn('dropdown', className)} ref={ref}>
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
