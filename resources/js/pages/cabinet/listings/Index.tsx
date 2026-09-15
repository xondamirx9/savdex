import { router, useForm } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { Eye, Package, Pencil, Plus, Rocket, ShoppingCart, TriangleAlert } from 'lucide-react';
import { useState } from 'react';
import { Empty, Tabs, formatNumber } from '@/components/cabinet';
import { useConfirm } from '@/components/useConfirm';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { cn } from '@/lib/cn';
import { t, tChoice } from '@/lib/i18n';
import { routes } from '@/routes';

interface Row {
    id: number;
    slug: string | null;
    title: string;
    type: 'supply' | 'demand';
    category: string | null;
    price: number | null;
    currency: string;
    unit: string | null;
    negotiable: boolean;
    status: string;
    moderation_note: string | null;
    impressions: number;
    views: number;
    unlocks: number;
    expires_at: string | null;
    expiring_soon: boolean;
    badges: string[];
}

interface Props {
    listings: Row[];
    counts: Record<string, number>;
    tabs: Record<string, string>;
    status: string;
    limit: { used: number; total: number | null } | null;
}

/* Подпись берётся из словаря по тому же ключу, что и статус: цвет
   здесь, текст — в переводе, иначе список статусов пришлось бы держать
   в двух местах и следить, чтобы они не разъехались. */
const STATUS_BADGE: Record<string, string> = {
    active: 'badge-verified',
    moderation: 'badge-neutral',
    draft: 'badge-neutral',
    expired: 'badge-neutral',
    rejected: 'badge-danger',
    archived: 'badge-neutral',
};

function priceLabel(row: Row): string {
    if (row.negotiable || row.price === null) return t('cabinet.listings.negotiable');

    const amount = formatNumber(row.price);
    const currency = row.currency === 'UZS' ? t('catalog.currency_uzs') : row.currency;

    return row.unit ? `${amount} ${currency}/${row.unit}` : `${amount} ${currency}`;
}

export default function ListingsIndex({ listings, counts, tabs, status, limit }: Props) {
    const [selected, setSelected] = useState<number[]>([]);
    const { confirm, dialog } = useConfirm();
    const bulk = useForm<{ action: string; ids: number[] }>({ action: '', ids: [] });

    function switchTab(key: string) {
        setSelected([]);
        router.get(routes.cabinetListings, { status: key }, { preserveState: true, preserveScroll: true });
    }

    function toggle(id: number) {
        setSelected((s) => (s.includes(id) ? s.filter((x) => x !== id) : [...s, id]));
    }

    function send(action: 'renew' | 'archive' | 'delete') {
        bulk.transform(() => ({ action, ids: selected }));
        bulk.post('/cabinet/listings/bulk', {
            preserveScroll: true,
            onSuccess: () => setSelected([]),
        });
    }

    function runBulk(action: 'renew' | 'archive' | 'delete') {
        if (selected.length === 0) return;

        // Удаление необратимо, поэтому спрашиваем — в отличие от продления
        if (action !== 'delete') {
            send(action);

            return;
        }

        confirm({
            title: tChoice('cabinet.listings.delete_title', selected.length),
            description: t('cabinet.listings.delete_text'),
            confirmLabel: t('common.delete'),
            danger: true,
            onConfirm: () => send('delete'),
        });
    }

    const tabItems = Object.entries(tabs).map(([key, label]) => ({ key, label, count: counts[key] ?? 0 }));
    const allChecked = listings.length > 0 && selected.length === listings.length;

    return (
        <CabinetLayout
            title={t('cabinet.listings.title')}
            heading={t('cabinet.listings.title')}
            subheading={
                limit
                    ? limit.total === null
                        ? t('cabinet.listings.limit_unlimited', { used: limit.used })
                        : t('cabinet.listings.limit', { used: limit.used, total: limit.total })
                    : undefined
            }
            actions={
                <Link href={routes.listingCreate} className="btn btn-primary">
                    <Plus aria-hidden className="size-4" /> {t('cabinet.listings.create')}
                </Link>
            }
        >
            {dialog}

            <Tabs items={tabItems} active={status} onChange={switchTab} label={t('cabinet.listings.tabs_label')} />

            {listings.length === 0 ? (
                <Empty
                    icon={Package}
                    title={status === 'active' ? t('cabinet.listings.empty') : t('cabinet.listings.empty_tab')}
                    text={
                        status === 'active'
                            ? t('cabinet.listings.empty_text')
                            : t('cabinet.listings.empty_tab_text')
                    }
                    action={
                        status === 'active'
                            ? { href: routes.listingCreate, label: t('cabinet.listings.create') }
                            : undefined
                    }
                />
            ) : (
                <>
                    {/* Массовые действия имеют смысл только там, где есть что
                        продлевать или снимать: у черновика нет срока */}
                    {(status === 'active' || status === 'expired') && (
                        <div className="row wrap" style={{ gap: 10, marginBottom: 16 }}>
                            <label className="check">
                                <input
                                    type="checkbox"
                                    checked={allChecked}
                                    onChange={(e) => setSelected(e.target.checked ? listings.map((l) => l.id) : [])}
                                />
                                {t('cabinet.listings.select_all')}
                            </label>
                            <button
                                className="btn btn-secondary btn-sm"
                                disabled={selected.length === 0 || bulk.processing}
                                onClick={() => runBulk('renew')}
                            >
                                {t('cabinet.listings.renew')}
                                {selected.length > 0 && ` (${selected.length})`}
                            </button>
                            <button
                                className="btn btn-secondary btn-sm"
                                disabled={selected.length === 0 || bulk.processing}
                                onClick={() => runBulk('archive')}
                            >
                                {t('cabinet.listings.archive')}
                            </button>
                            <button
                                className="btn btn-secondary btn-sm"
                                disabled={selected.length === 0 || bulk.processing}
                                onClick={() => runBulk('delete')}
                            >
                                {t('common.delete')}
                            </button>
                        </div>
                    )}

                    {status === 'rejected' && listings[0]?.moderation_note && (
                        <div className="alert alert-danger" style={{ marginBottom: 16 }}>
                            <TriangleAlert aria-hidden className="size-5" />
                            <div>
                                <b>{t('cabinet.listings.rejected', { title: listings[0].title })}</b>
                                <br />
                                {t('cabinet.listings.reason', { reason: listings[0].moderation_note })}
                            </div>
                        </div>
                    )}

                    <div className="table-wrap table-cards">
                        <table className="table table-listings">
                            <thead>
                                <tr>
                                    {(status === 'active' || status === 'expired') && (
                                        <th style={{ width: 34 }}>
                                            <span className="sr-only">{t('cabinet.listings.col_select')}</span>
                                        </th>
                                    )}
                                    <th>{t('cabinet.listings.col_listing')}</th>
                                    <th>{t('cabinet.listings.col_status')}</th>
                                    <th className="num">{t('cabinet.listings.col_impressions')}</th>
                                    <th className="num">{t('cabinet.listings.col_views')}</th>
                                    <th className="num">{t('cabinet.listings.col_unlocks')}</th>
                                    <th>{t('cabinet.listings.col_until')}</th>
                                    <th>
                                        <span className="sr-only">{t('cabinet.listings.col_actions')}</span>
                                    </th>
                                </tr>
                            </thead>
                            <tbody>
                                {listings.map((row) => {
                                    const badgeClass = STATUS_BADGE[row.status] ?? STATUS_BADGE.draft;
                                    const TypeIcon = row.type === 'demand' ? ShoppingCart : Package;

                                    return (
                                        <tr key={row.id}>
                                            {(status === 'active' || status === 'expired') && (
                                                <td data-label="">
                                                    <input
                                                        type="checkbox"
                                                        aria-label={t('cabinet.listings.select_one', {
                                                            title: row.title,
                                                        })}
                                                        checked={selected.includes(row.id)}
                                                        onChange={() => toggle(row.id)}
                                                    />
                                                </td>
                                            )}

                                            <td data-label={t('cabinet.listings.col_listing')}>
                                                <div className="row" style={{ gap: 10 }}>
                                                    <span
                                                        className={cn(
                                                            'ico-box ico-box-sm',
                                                            row.type === 'demand' && 'ico-box-demand',
                                                        )}
                                                    >
                                                        <TypeIcon aria-hidden className="size-4" />
                                                    </span>
                                                    <span style={{ minWidth: 0 }}>
                                                        {/* Название ведёт на страницу объявления — так его
                                                            видят покупатели (для неопубликованных это
                                                            предпросмотр). Редактирование — карандашом справа.
                                                            У свежего черновика страницы ещё нет — тогда
                                                            в редактор */}
                                                        <Link
                                                            href={row.slug ? routes.listing(row.slug) : routes.listingEdit(row.id)}
                                                            className="listing-title-link"
                                                        >
                                                            {row.title}
                                                        </Link>
                                                        <br />
                                                        <span className="t-caption muted">
                                                            {row.category ?? t('cabinet.listings.no_category')} ·{' '}
                                                            {priceLabel(row)}
                                                        </span>
                                                    </span>
                                                </div>
                                            </td>

                                            <td data-label={t('cabinet.listings.col_status')}>
                                                <span className={cn('badge', badgeClass)}>
                                                    {t(`cabinet.listings.status_${row.status}`)}
                                                </span>{' '}
                                                {row.badges.map((b) => (
                                                    <span key={b} className="badge badge-top">
                                                        {b}
                                                    </span>
                                                ))}
                                            </td>

                                            <td data-label={t('cabinet.listings.col_impressions')} className="num">
                                                {formatNumber(row.impressions)}
                                            </td>
                                            <td data-label={t('cabinet.listings.col_views')} className="num">
                                                {formatNumber(row.views)}
                                            </td>
                                            <td data-label={t('cabinet.listings.col_unlocks')} className="num">
                                                {row.unlocks}
                                            </td>

                                            <td data-label={t('cabinet.listings.col_until')}>
                                                {row.expires_at ? (
                                                    <span
                                                        style={
                                                            row.expiring_soon
                                                                ? { color: 'var(--danger)', fontWeight: 600 }
                                                                : undefined
                                                        }
                                                    >
                                                        {row.expires_at}
                                                    </span>
                                                ) : (
                                                    <span className="muted">—</span>
                                                )}
                                            </td>

                                            <td data-label="">
                                                <div className="row" style={{ gap: 4, justifyContent: 'flex-end' }}>
                                                    {row.status === 'rejected' ? (
                                                        <button
                                                            className="btn btn-primary btn-sm"
                                                            onClick={() =>
                                                                router.post(`/cabinet/listings/${row.id}/resubmit`, {}, { preserveScroll: true })
                                                            }
                                                        >
                                                            {t('cabinet.listings.resubmit')}
                                                        </button>
                                                    ) : row.expiring_soon || row.status === 'expired' ? (
                                                        <button
                                                            className="btn btn-primary btn-sm"
                                                            onClick={() =>
                                                                router.post(`/cabinet/listings/${row.id}/renew`, {}, { preserveScroll: true })
                                                            }
                                                        >
                                                            {t('cabinet.listings.renew')}
                                                        </button>
                                                    ) : row.status === 'active' ? (
                                                        <Link
                                                            href={routes.cabinetPromo}
                                                            className="btn btn-ghost btn-icon"
                                                            aria-label={t('cabinet.listings.promote_one', {
                                                                title: row.title,
                                                            })}
                                                        >
                                                            <Rocket aria-hidden className="size-5" />
                                                        </Link>
                                                    ) : null}

                                                    {row.slug && (
                                                        <Link
                                                            href={routes.listing(row.slug)}
                                                            className="btn btn-ghost btn-icon"
                                                            aria-label={
                                                                row.status === 'active'
                                                                    ? t('cabinet.listings.view_one', {
                                                                          title: row.title,
                                                                      })
                                                                    : t('cabinet.listings.preview_one', {
                                                                          title: row.title,
                                                                      })
                                                            }
                                                            title={
                                                                row.status === 'active'
                                                                    ? t('cabinet.listings.view')
                                                                    : t('cabinet.listings.preview')
                                                            }
                                                        >
                                                            <Eye aria-hidden className="size-5" />
                                                        </Link>
                                                    )}

                                                    <Link
                                                        href={routes.listingEdit(row.id)}
                                                        className="btn btn-ghost btn-icon"
                                                        aria-label={t('cabinet.listings.edit_one', {
                                                            title: row.title,
                                                        })}
                                                    >
                                                        <Pencil aria-hidden className="size-5" />
                                                    </Link>
                                                </div>
                                            </td>
                                        </tr>
                                    );
                                })}
                            </tbody>
                        </table>
                    </div>
                </>
            )}
        </CabinetLayout>
    );
}
