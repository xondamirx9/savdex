import { Building2, CalendarDays, MapPin, Wallet } from 'lucide-react';
import { Link } from '@/components/ui/Link';
import { cn } from '@/lib/cn';
import { t, tChoice } from '@/lib/i18n';
import { getLocale } from '@/lib/locale';
import { routes } from '@/routes';

/**
 * Карточка тендера — одна на ленту каталога, блок похожих
 * и страницу самого тендера.
 */
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
