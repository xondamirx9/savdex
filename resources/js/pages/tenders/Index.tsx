import { router } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { Building2, CalendarDays, MapPin, Search, Wallet } from 'lucide-react';
import { useState } from 'react';
import { BoardFilter } from '@/components/BoardFilter';
import { PublicLayout } from '@/layouts/PublicLayout';
import { cn } from '@/lib/cn';
import { t, tChoice } from '@/lib/i18n';
import { getLocale } from '@/lib/locale';
import { routes } from '@/routes';

export interface TenderRow {
    id: number;
    slug: string;
    title: string;
    excerpt: string;
    customer: string | null;
    category: string | null;
    country: string | null;
    location: string | null;
    budget: number | null;
    currency: string;
    deadline: string | null;
    days_left: number | null;
    closed: boolean;
    published: string | null;
}

interface Props {
    tenders: {
        data: TenderRow[];
        links: { url: string | null; label: string; active: boolean }[];
        current_page: number;
        last_page: number;
    };
    filters: { q: string; category: number | null; closed: boolean };
    categories: { id: number; name: string; children: { id: number; name: string }[] }[];
    total: number;
}

/** «250 000 000 сум» — бюджет в формате языка витрины. */
export function budgetLabel(budget: number | null, currency: string): string {
    if (budget === null) return t('tenders.budget_none');

    const amount = new Intl.NumberFormat(getLocale() === 'ru' ? 'ru-RU' : getLocale()).format(budget);

    return `${amount} ${currency === 'UZS' ? t('catalog.currency_uzs') : currency}`;
}

/** Срок подачи: дней осталось, «завершён» или дата, если далеко. */
export function deadlineBadge(row: Pick<TenderRow, 'deadline' | 'days_left' | 'closed'>) {
    if (row.deadline === null) {
        return <span className="badge badge-neutral">{t('tenders.deadline_none')}</span>;
    }

    if (row.closed) {
        return <span className="badge badge-neutral">{t('tenders.closed')}</span>;
    }

    const soon = row.days_left !== null && row.days_left <= 7;

    return (
        <span className={cn('badge', soon ? 'badge-warning' : 'badge-supply')}>
            {row.days_left === 0
                ? t('tenders.last_day')
                : tChoice('tenders.days_left', row.days_left ?? 0)}
        </span>
    );
}

export function TenderCard({ row }: { row: TenderRow }) {
    const place = [row.location, row.country].filter(Boolean).join(', ');

    return (
        <Link
            href={routes.tender(row.slug)}
            className="card lift"
            style={{ display: 'flex', flexDirection: 'column', gap: 12, color: 'inherit' }}
        >
            <div className="row wrap" style={{ gap: 8 }}>
                {deadlineBadge(row)}
                {row.category && <span className="badge badge-neutral">{row.category}</span>}
            </div>

            <h3 className="t-h4">{row.title}</h3>

            {row.excerpt && (
                <p className="t-sm muted" style={{ flex: 1 }}>
                    {row.excerpt}
                </p>
            )}

            <dl className="t-sm" style={{ display: 'grid', gap: 6, margin: 0 }}>
                {row.customer && (
                    <div className="row" style={{ gap: 8 }}>
                        <Building2 aria-hidden className="size-4 muted" />
                        <dt className="sr-only">{t('tenders.customer')}</dt>
                        <dd style={{ margin: 0 }}>{row.customer}</dd>
                    </div>
                )}
                <div className="row" style={{ gap: 8 }}>
                    <Wallet aria-hidden className="size-4 muted" />
                    <dt className="sr-only">{t('tenders.budget')}</dt>
                    <dd style={{ margin: 0, fontWeight: 600 }}>{budgetLabel(row.budget, row.currency)}</dd>
                </div>
                {row.deadline && (
                    <div className="row" style={{ gap: 8 }}>
                        <CalendarDays aria-hidden className="size-4 muted" />
                        <dt className="sr-only">{t('tenders.deadline')}</dt>
                        <dd style={{ margin: 0 }}>
                            {t('tenders.deadline')}: {row.deadline}
                        </dd>
                    </div>
                )}
                {place && (
                    <div className="row" style={{ gap: 8 }}>
                        <MapPin aria-hidden className="size-4 muted" />
                        <dt className="sr-only">{t('tenders.location')}</dt>
                        <dd style={{ margin: 0 }}>{place}</dd>
                    </div>
                )}
            </dl>
        </Link>
    );
}

export default function TendersIndex({ tenders, filters, categories, total }: Props) {
    const [q, setQ] = useState(filters.q);

    function apply(next: Partial<Props['filters']>) {
        router.get(
            routes.tenders,
            Object.fromEntries(
                Object.entries({ ...filters, ...next }).filter(([, v]) => v !== '' && v !== null && v !== false),
            ),
            { preserveState: true, preserveScroll: true, replace: true },
        );
    }

    return (
        <PublicLayout title={t('tenders.meta_title')} description={t('tenders.meta_description')}>
            <div className="container board-page">
                <div className="section-head-left" style={{ marginBottom: 20 }}>
                    <span className="eyebrow">{t('tenders.eyebrow')}</span>
                    {/* Заголовок на ступень мельче витринного: страница
                        служебная, и крупная шапка оттягивала внимание
                        от самих тендеров */}
                    <h1 className="t-h1">{t('tenders.h1')}</h1>
                    <p className="t-body muted">{t('tenders.lead')}</p>
                </div>

                <div className="board-layout">
                    <BoardFilter
                        title={t('tenders.category')}
                        value={filters.category === null ? '' : String(filters.category)}
                        onPick={(id) => apply({ category: id === '' ? null : Number(id) })}
                        options={categories.map((parent) => ({
                            id: String(parent.id),
                            label: parent.name,
                            children: parent.children.map((child) => ({
                                id: String(child.id),
                                label: child.name,
                            })),
                        }))}
                    />

                    <div className="board-main">
                        <div className="toolbar">
                            <div className="board-search">
                                <label htmlFor="tender-q" className="sr-only">
                                    {t('tenders.search_label')}
                                </label>
                                <input
                                    id="tender-q"
                                    className="input"
                                    type="search"
                                    placeholder={t('tenders.search_placeholder')}
                                    style={{ paddingLeft: 42 }}
                                    value={q}
                                    onChange={(e) => setQ(e.target.value)}
                                    onKeyDown={(e) => e.key === 'Enter' && apply({ q })}
                                />
                                <span aria-hidden className="board-search-ico">
                                    <Search className="size-5" />
                                </span>
                            </div>
                        </div>

                        {/* Состояние приёма заявок — под поиском: это
                            переключатель того же списка, а не отдельный
                            раздел, как читалось в панели слева */}
                        <div className="board-tabs">
                            <button
                                type="button"
                                className={cn('chip', !filters.closed && 'chip-active')}
                                aria-pressed={!filters.closed}
                                onClick={() => apply({ closed: false })}
                            >
                                {t('tenders.tab_open')}
                            </button>
                            <button
                                type="button"
                                className={cn('chip', filters.closed && 'chip-active')}
                                aria-pressed={filters.closed}
                                onClick={() => apply({ closed: true })}
                            >
                                {t('tenders.tab_closed')}
                            </button>
                            {filters.category !== null && (
                                <button type="button" className="chip" onClick={() => apply({ category: null })}>
                                    {t('tenders.reset')}
                                </button>
                            )}
                            <span className="t-sm muted board-count">{tChoice('tenders.found', total)}</span>
                        </div>

                        {tenders.data.length === 0 ? (
                            <div className="card empty">
                                <div className="empty-icon">
                                    <Building2 aria-hidden className="size-7" />
                                </div>
                                <p className="t-h4">{t('tenders.empty_title')}</p>
                                <p className="t-sm muted mt-8" style={{ maxWidth: 420, margin: '8px auto 0' }}>
                                    {t('tenders.empty_text')}
                                </p>
                            </div>
                        ) : (
                            <div className="grid grid-3" data-reveal-stagger>
                                {tenders.data.map((row) => (
                                    <TenderCard key={row.id} row={row} />
                                ))}
                            </div>
                        )}

                        {tenders.last_page > 1 && (
                            <nav className="pagination mt-32" aria-label={t('tenders.pages')}>
                                {tenders.links.map((link, i) =>
                                    link.url ? (
                                        <Link
                                            key={i}
                                            href={link.url}
                                            className={cn('page-link', link.active && 'is-active')}
                                            aria-current={link.active ? 'page' : undefined}
                                            dangerouslySetInnerHTML={{ __html: link.label }}
                                        />
                                    ) : (
                                        <span
                                            key={i}
                                            className="page-link is-disabled"
                                            aria-disabled="true"
                                            dangerouslySetInnerHTML={{ __html: link.label }}
                                        />
                                    ),
                                )}
                            </nav>
                        )}
                    </div>
                </div>
            </div>
        </PublicLayout>
    );
}
