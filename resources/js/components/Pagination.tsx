import { ChevronLeft, ChevronRight } from 'lucide-react';
import type { ReactNode } from 'react';

import { Link } from '@/components/ui/Link';
import { cn } from '@/lib/cn';
import { t } from '@/lib/i18n';

export type PaginatorLink = { url: string | null; label: string; active: boolean };

/**
 * Адрес страницы без хоста. Пагинатор отдаёт полный адрес
 * (http://…/companies?page=2), а языковой префикс Link подставляет
 * только в путь от корня — и на /en/companies ссылки вели на русскую
 * версию.
 */
function relative(url: string): string {
    const match = url.match(/^https?:\/\/[^/]+(\/.*)?$/);

    return match ? (match[1] ?? '/') : url;
}

/** Сколько номеров показывать по обе стороны от текущей страницы */
const AROUND = 1;

type Item = { kind: 'page'; page: number; url: string | null; active: boolean } | { kind: 'gap'; key: string };

/**
 * Номера страниц, которые видны: первая, последняя и соседи текущей,
 * между ними — «…». Разрыв в одну страницу закрывается самой страницей:
 * «1 … 3» хуже, чем «1 2 3».
 */
function pageItems(pages: Map<number, string | null>, current: number, last: number): Item[] {
    const wanted = new Set<number>([1, last]);

    for (let n = current - AROUND; n <= current + AROUND; n++) {
        if (n >= 1 && n <= last) wanted.add(n);
    }

    // Разрыв ровно в одну страницу — показываем её вместо «…»
    for (const n of [...wanted]) {
        if (wanted.has(n + 2) && !wanted.has(n + 1)) wanted.add(n + 1);
    }

    const items: Item[] = [];
    let previous = 0;

    for (const n of [...wanted].sort((a, b) => a - b)) {
        // Номера, до которых сервер не дал ссылки, пропускаем: сервер
        // окно шире нашего, так что сюда попадают только чужие адреса
        if (!pages.has(n) && n !== current) continue;

        if (previous && n - previous > 1) items.push({ kind: 'gap', key: `gap-${previous}` });

        items.push({ kind: 'page', page: n, url: pages.get(n) ?? null, active: n === current });
        previous = n;
    }

    return items;
}

/**
 * Постраничная навигация по ссылкам пагинатора Laravel (и его копии
 * в Django): первая ссылка — «назад», последняя — «вперёд», между
 * ними номера и «...».
 *
 * Подписи «назад/вперёд» берём из своего словаря, а не из ссылок:
 * у площадки нет файла pagination, и на всех языках, кроме
 * английского, сервер отдавал ключ «pagination.previous» как есть.
 */
export function Pagination({ links, label, className }: { links: PaginatorLink[]; label: string; className?: string }) {
    if (links.length < 3) return null;

    const prev = links[0];
    const next = links[links.length - 1];
    const pages = new Map<number, string | null>();
    let current = 1;

    for (const link of links.slice(1, -1)) {
        const n = Number(link.label);

        if (!Number.isInteger(n)) continue;

        pages.set(n, link.url);
        if (link.active) current = n;
    }

    const last = Math.max(...pages.keys(), 1);

    if (last <= 1) return null;

    return (
        <nav className={cn('pagination', className)} aria-label={label}>
            <Step url={prev.url} rel="prev">
                <ChevronLeft aria-hidden className="size-4" />
                <span className="page-step-text">{t('common.prev_page')}</span>
            </Step>

            {pageItems(pages, current, last).map((item) =>
                item.kind === 'gap' ? (
                    <span key={item.key} className="page-gap" aria-hidden>
                        …
                    </span>
                ) : item.active || !item.url ? (
                    <span
                        key={item.page}
                        className={cn('page-link', item.active && 'is-active')}
                        aria-current={item.active ? 'page' : undefined}
                        aria-label={t('common.page_n', { page: item.page })}
                    >
                        {item.page}
                    </span>
                ) : (
                    <Link key={item.page} href={relative(item.url)} className="page-link" aria-label={t('common.page_n', { page: item.page })}>
                        {item.page}
                    </Link>
                ),
            )}

            <Step url={next.url} rel="next">
                <span className="page-step-text">{t('common.next_page')}</span>
                <ChevronRight aria-hidden className="size-4" />
            </Step>
        </nav>
    );
}

/** «Назад» и «Вперёд»: на крайней странице — не ссылка, а неактивная кнопка */
function Step({ url, rel, children }: { url: string | null; rel: 'prev' | 'next'; children: ReactNode }) {
    const title = rel === 'prev' ? t('common.prev_page') : t('common.next_page');

    if (!url) {
        return (
            <span className="page-link page-step is-disabled" aria-disabled="true" aria-label={title}>
                {children}
            </span>
        );
    }

    return (
        <Link href={relative(url)} rel={rel} className="page-link page-step" aria-label={title}>
            {children}
        </Link>
    );
}
