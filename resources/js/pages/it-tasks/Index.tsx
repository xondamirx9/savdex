import { router } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { Building2, CalendarDays, CheckCircle2, ChevronDown, Code2, ExternalLink, Menu, MessageSquareText, Search, Wallet } from 'lucide-react';
import { useState } from 'react';
import { PublicLayout } from '@/layouts/PublicLayout';
import { cn } from '@/lib/cn';
import { t, tChoice } from '@/lib/i18n';
import { getLocale } from '@/lib/locale';
import { useDismiss } from '@/lib/useDismiss';
import { routes } from '@/routes';

export interface TaskRow {
    id: number;
    slug: string;
    title: string;
    excerpt: string;
    service_type: string;
    service_label: string;
    stack: string[];
    budget_type: 'fixed' | 'range' | 'negotiable';
    budget_from: number | null;
    budget_to: number | null;
    currency: string;
    deadline: string | null;
    published: string | null;
    responses: number;
    active: boolean;
    completed: boolean;
    completed_on: string | null;
    result_url: string | null;
    result_host: string | null;
    result_summary: string | null;
    contractor: { name: string; slug: string; initials: string; logo: string | null } | null;
    company: {
        name: string;
        slug: string;
        initials: string;
        logo: string | null;
        verified: boolean;
        city: string | null;
    } | null;
}

interface Props {
    tasks: {
        data: TaskRow[];
        links: { url: string | null; label: string; active: boolean }[];
        current_page: number;
        last_page: number;
    };
    filters: { q: string; type: string; done: boolean };
    types: { code: string; label: string }[];
    total: number;
    viewer: { guest: boolean; provider: boolean };
}

function money(value: number): string {
    return new Intl.NumberFormat(getLocale() === 'ru' ? 'ru-RU' : getLocale()).format(value);
}

/** «20 000 000 – 50 000 000 сум», «от 5 000 000 сум» или «договорной». */
export function budgetLabel(row: Pick<TaskRow, 'budget_type' | 'budget_from' | 'budget_to' | 'currency'>): string {
    const cur = row.currency === 'UZS' ? t('catalog.currency_uzs') : row.currency;

    if (row.budget_type === 'range' && row.budget_from !== null && row.budget_to !== null) {
        return `${money(row.budget_from)} – ${money(row.budget_to)} ${cur}`;
    }

    if (row.budget_type === 'fixed' && row.budget_from !== null) {
        return `${money(row.budget_from)} ${cur}`;
    }

    return t('it_tasks.budget_negotiable');
}

export function TaskCard({ row }: { row: TaskRow }) {
    return (
        <Link
            href={routes.itTask(row.slug)}
            className="card lift"
            style={{ display: 'flex', flexDirection: 'column', gap: 12, color: 'inherit' }}
        >
            <div className="row wrap" style={{ gap: 8 }}>
                <span className="badge badge-supply">{row.service_label}</span>
                {row.completed ? (
                    <span className="badge badge-verified">
                        <CheckCircle2 aria-hidden className="size-3.5" /> {t('it_tasks.completed')}
                    </span>
                ) : (
                    row.published && <span className="t-caption muted">{row.published}</span>
                )}
            </div>

            <h3 className="t-h4">{row.title}</h3>

            {row.completed && row.result_summary ? (
                <p className="t-sm" style={{ flex: 1 }}>
                    {row.result_summary}
                </p>
            ) : (
                row.excerpt && (
                    <p className="t-sm muted" style={{ flex: 1 }}>
                        {row.excerpt}
                    </p>
                )
            )}

            {row.completed && row.result_host && (
                <span className="row t-sm" style={{ gap: 6, color: 'var(--primary-700)', fontWeight: 600 }}>
                    <ExternalLink aria-hidden className="size-4" /> {row.result_host}
                </span>
            )}

            {row.stack.length > 0 && (
                <div className="row wrap" style={{ gap: 4 }}>
                    {row.stack.slice(0, 6).map((s) => (
                        <span key={s} className="badge badge-neutral">{s}</span>
                    ))}
                </div>
            )}

            <dl className="t-sm" style={{ display: 'grid', gap: 6, margin: 0 }}>
                <div className="row" style={{ gap: 8 }}>
                    <Wallet aria-hidden className="size-4 muted" />
                    <dt className="sr-only">{t('it_tasks.budget')}</dt>
                    <dd style={{ margin: 0, fontWeight: 600 }}>{budgetLabel(row)}</dd>
                </div>
                {row.deadline && (
                    <div className="row" style={{ gap: 8 }}>
                        <CalendarDays aria-hidden className="size-4 muted" />
                        <dt className="sr-only">{t('it_tasks.deadline')}</dt>
                        <dd style={{ margin: 0 }}>
                            {t('it_tasks.deadline')}: {row.deadline}
                        </dd>
                    </div>
                )}
                {row.company && (
                    <div className="row" style={{ gap: 8 }}>
                        <Building2 aria-hidden className="size-4 muted" />
                        <dt className="sr-only">{t('it_tasks.customer')}</dt>
                        <dd style={{ margin: 0 }}>
                            {row.company.name}
                            {row.company.city ? `, ${row.company.city}` : ''}
                        </dd>
                    </div>
                )}
                {row.completed && row.contractor && (
                    <div className="row" style={{ gap: 8 }}>
                        <Code2 aria-hidden className="size-4 muted" />
                        <dt className="sr-only">{t('it_tasks.contractor')}</dt>
                        <dd style={{ margin: 0 }}>
                            {t('it_tasks.contractor')}: {row.contractor.name}
                        </dd>
                    </div>
                )}
                {!row.completed && (
                    <div className="row" style={{ gap: 8 }}>
                        <MessageSquareText aria-hidden className="size-4 muted" />
                        <dd style={{ margin: 0 }} className="muted">
                            {tChoice('it_tasks.responses', row.responses)}
                        </dd>
                    </div>
                )}
            </dl>
        </Link>
    );
}

/**
 * Вид услуги — меню-бургер рядом с поиском.
 *
 * Раньше список жил в боковой панели и прокручивался внутри себя:
 * на десяток видов услуг приходилось два вложенных скролла, а на
 * телефоне панель занимала первый экран целиком. В меню виден
 * выбранный вид, а остальные открываются по нажатию.
 */
function TypeMenu({
    types,
    value,
    onPick,
}: {
    types: Props['types'];
    value: string;
    onPick: (code: string) => void;
}) {
    const [open, setOpen] = useState(false);
    const ref = useDismiss(() => setOpen(false));
    const current = types.find((type) => type.code === value);

    return (
        <div className="dropdown type-menu" ref={ref}>
            <button
                type="button"
                className="type-menu-btn"
                aria-expanded={open}
                aria-haspopup="true"
                aria-label={t('it_tasks.filters')}
                onClick={(e) => {
                    e.stopPropagation();
                    setOpen((v) => !v);
                }}
            >
                <Menu aria-hidden className="size-4" />
                <span className="type-menu-value">{current?.label ?? t('it_tasks.all_types')}</span>
                <ChevronDown aria-hidden className="size-4" />
            </button>
            <div className={cn('dropdown-menu type-menu-list', open && 'open')} aria-label={t('it_tasks.filters')}>
                <button
                    type="button"
                    className="dropdown-item"
                    aria-selected={value === ''}
                    onClick={() => {
                        onPick('');
                        setOpen(false);
                    }}
                >
                    {t('it_tasks.all_types')}
                </button>
                {types.map((type) => (
                    <button
                        key={type.code}
                        type="button"
                        className="dropdown-item"
                        aria-selected={value === type.code}
                        onClick={() => {
                            onPick(type.code);
                            setOpen(false);
                        }}
                    >
                        {type.label}
                    </button>
                ))}
            </div>
        </div>
    );
}

export default function ItTasksIndex({ tasks, filters, types, total, viewer }: Props) {
    const [q, setQ] = useState(filters.q);

    function apply(next: Partial<Props['filters']>) {
        router.get(
            routes.itTasks,
            Object.fromEntries(
                Object.entries({ ...filters, ...next }).filter(([, v]) => v !== '' && v !== null && v !== false),
            ),
            { preserveState: true, preserveScroll: true, replace: true },
        );
    }

    return (
        <PublicLayout title={t('it_tasks.meta_title')} description={t('it_tasks.meta_description')}>
            <div className="container it-tasks">
                <div className="section-head-left" style={{ marginBottom: 20 }}>
                    <span className="eyebrow">{t('it_tasks.eyebrow')}</span>
                    {/* Заголовок и подзаголовок на ступень мельче обычной
                        витрины: страница служебная, и крупная шапка
                        оттягивала внимание от самих задач */}
                    <h1 className="t-h1">{t('it_tasks.h1')}</h1>
                    <p className="t-body muted">{t('it_tasks.lead')}</p>
                    <p className="t-sm muted" style={{ marginTop: 6 }}>{t('it_tasks.post_hint')}</p>
                </div>

                <div className="toolbar">
                    <TypeMenu types={types} value={filters.type} onPick={(type) => apply({ type })} />

                    <div className="it-search">
                        <label htmlFor="it-q" className="sr-only">
                            {t('it_tasks.search_label')}
                        </label>
                        <input
                            id="it-q"
                            className="input"
                            type="search"
                            placeholder={t('it_tasks.search_placeholder')}
                            style={{ paddingLeft: 42 }}
                            value={q}
                            onChange={(e) => setQ(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && apply({ q })}
                        />
                        <span aria-hidden className="it-search-ico">
                            <Search className="size-5" />
                        </span>
                    </div>

                    <Link href={viewer.guest ? routes.login : routes.itTaskCreate} className="btn btn-primary">
                        {t('it_tasks.post_task')}
                    </Link>
                </div>

                {/* Состояние задач — под поиском: это переключатель того же
                    списка, а не отдельный раздел, как читалось в панели */}
                <div className="it-tabs">
                    <button
                        type="button"
                        className={cn('chip', !filters.done && 'chip-active')}
                        aria-pressed={!filters.done}
                        onClick={() => apply({ done: false })}
                    >
                        {t('it_tasks.tab_open')}
                    </button>
                    <button
                        type="button"
                        className={cn('chip', filters.done && 'chip-active')}
                        aria-pressed={filters.done}
                        onClick={() => apply({ done: true })}
                    >
                        {t('it_tasks.tab_done')}
                    </button>
                    {filters.type !== '' && (
                        <button type="button" className="chip" onClick={() => apply({ type: '' })}>
                            {t('it_tasks.reset')}
                        </button>
                    )}
                    <span className="t-sm muted it-count">{tChoice('it_tasks.found', total)}</span>
                </div>

                {tasks.data.length === 0 ? (
                    <div className="card empty">
                        <div className="empty-icon">
                            <Code2 aria-hidden className="size-7" />
                        </div>
                        <p className="t-h4">{filters.done ? t('it_tasks.done_empty_title') : t('it_tasks.empty_title')}</p>
                        <p className="t-sm muted mt-8" style={{ maxWidth: 420, margin: '8px auto 0' }}>
                            {filters.done ? t('it_tasks.done_empty_text') : t('it_tasks.empty_text')}
                        </p>
                    </div>
                ) : (
                    <div className="grid grid-3" data-reveal-stagger>
                        {tasks.data.map((row) => (
                            <TaskCard key={row.id} row={row} />
                        ))}
                    </div>
                )}

                {tasks.last_page > 1 && (
                    <nav className="pagination mt-32" aria-label={t('it_tasks.pages')}>
                        {tasks.links.map((link, i) =>
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
        </PublicLayout>
    );
}
