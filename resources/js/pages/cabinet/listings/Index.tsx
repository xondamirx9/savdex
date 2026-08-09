import { router, useForm } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { Clock, Package, Pencil, Plus, Rocket, ShoppingCart, TriangleAlert } from 'lucide-react';
import { useState } from 'react';
import { Empty, Tabs, formatNumber } from '@/components/cabinet';
import { useConfirm } from '@/components/useConfirm';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { cn } from '@/lib/cn';
import { pluralize } from '@/lib/plural';
import { routes } from '@/routes';

interface Row {
    id: number;
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

const STATUS_BADGE: Record<string, { cls: string; label: string }> = {
    active: { cls: 'badge-verified', label: 'Активно' },
    moderation: { cls: 'badge-neutral', label: 'На проверке' },
    draft: { cls: 'badge-neutral', label: 'Черновик' },
    expired: { cls: 'badge-neutral', label: 'Истекло' },
    rejected: { cls: 'badge-danger', label: 'Отклонено' },
    archived: { cls: 'badge-neutral', label: 'Снято' },
};

function priceLabel(row: Row): string {
    if (row.negotiable || row.price === null) return 'цена договорная';

    const amount = formatNumber(row.price);
    const currency = row.currency === 'UZS' ? 'сум' : row.currency;

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
            title: `Удалить ${pluralize(selected.length, ['объявление', 'объявления', 'объявлений'])}?`,
            description: 'Вместе с ними исчезнут фотографии и статистика показов. Восстановить нельзя. Если объявления просто не нужны сейчас — снимите их с публикации, это обратимо.',
            confirmLabel: 'Удалить',
            danger: true,
            onConfirm: () => send('delete'),
        });
    }

    const tabItems = Object.entries(tabs).map(([key, label]) => ({ key, label, count: counts[key] ?? 0 }));
    const allChecked = listings.length > 0 && selected.length === listings.length;

    return (
        <CabinetLayout
            title="Мои объявления"
            heading="Мои объявления"
            subheading={
                limit
                    ? limit.total === null
                        ? `${limit.used} активных, тариф без ограничений`
                        : `${limit.used} активных из ${limit.total} доступных по тарифу`
                    : undefined
            }
            actions={
                <Link href={routes.listingCreate} className="btn btn-primary">
                    <Plus aria-hidden className="size-4" /> Создать объявление
                </Link>
            }
        >
            {dialog}

            <Tabs items={tabItems} active={status} onChange={switchTab} label="Статусы объявлений" />

            {listings.length === 0 ? (
                <Empty
                    icon={Package}
                    title={status === 'active' ? 'Активных объявлений нет' : 'Здесь пусто'}
                    text={
                        status === 'active'
                            ? 'Разместите предложение или запрос — покупатели находят компании именно через объявления.'
                            : 'В этой вкладке пока ничего нет.'
                    }
                    action={status === 'active' ? { href: routes.listingCreate, label: 'Создать объявление' } : undefined}
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
                                Выбрать все
                            </label>
                            <button
                                className="btn btn-secondary btn-sm"
                                disabled={selected.length === 0 || bulk.processing}
                                onClick={() => runBulk('renew')}
                            >
                                Продлить{selected.length > 0 && ` (${selected.length})`}
                            </button>
                            <button
                                className="btn btn-secondary btn-sm"
                                disabled={selected.length === 0 || bulk.processing}
                                onClick={() => runBulk('archive')}
                            >
                                Снять с публикации
                            </button>
                            <button
                                className="btn btn-secondary btn-sm"
                                disabled={selected.length === 0 || bulk.processing}
                                onClick={() => runBulk('delete')}
                            >
                                Удалить
                            </button>
                        </div>
                    )}

                    {status === 'rejected' && listings[0]?.moderation_note && (
                        <div className="alert alert-danger" style={{ marginBottom: 16 }}>
                            <TriangleAlert aria-hidden className="size-5" />
                            <div>
                                <b>«{listings[0].title}» — отклонено.</b>
                                <br />
                                Причина: {listings[0].moderation_note}
                            </div>
                        </div>
                    )}

                    {status === 'moderation' && (
                        <div className="alert alert-info" style={{ marginBottom: 16 }}>
                            <Clock aria-hidden className="size-5" />
                            <div>Проверка обычно занимает до 2 часов в рабочее время.</div>
                        </div>
                    )}

                    <div className="table-wrap table-cards">
                        <table className="table table-listings">
                            <thead>
                                <tr>
                                    {(status === 'active' || status === 'expired') && (
                                        <th style={{ width: 34 }}>
                                            <span className="sr-only">Выбор</span>
                                        </th>
                                    )}
                                    <th>Объявление</th>
                                    <th>Статус</th>
                                    <th className="num">Показы</th>
                                    <th className="num">Просмотры</th>
                                    <th className="num">Контакты</th>
                                    <th>До</th>
                                    <th>
                                        <span className="sr-only">Действия</span>
                                    </th>
                                </tr>
                            </thead>
                            <tbody>
                                {listings.map((row) => {
                                    const badge = STATUS_BADGE[row.status] ?? STATUS_BADGE.draft;
                                    const TypeIcon = row.type === 'demand' ? ShoppingCart : Package;

                                    return (
                                        <tr key={row.id}>
                                            {(status === 'active' || status === 'expired') && (
                                                <td data-label="">
                                                    <input
                                                        type="checkbox"
                                                        aria-label={`Выбрать «${row.title}»`}
                                                        checked={selected.includes(row.id)}
                                                        onChange={() => toggle(row.id)}
                                                    />
                                                </td>
                                            )}

                                            <td data-label="Объявление">
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
                                                        {/* Название кликабельно: иконка карандаша — цель
                                                            размером 20 px, а строка в таблице читается
                                                            как основной способ открыть объявление */}
                                                        <Link href={routes.listingEdit(row.id)} className="listing-title-link">
                                                            {row.title}
                                                        </Link>
                                                        <br />
                                                        <span className="t-caption muted">
                                                            {row.category ?? 'Без категории'} · {priceLabel(row)}
                                                        </span>
                                                    </span>
                                                </div>
                                            </td>

                                            <td data-label="Статус">
                                                <span className={cn('badge', badge.cls)}>{badge.label}</span>{' '}
                                                {row.badges.map((b) => (
                                                    <span key={b} className="badge badge-top">
                                                        {b}
                                                    </span>
                                                ))}
                                            </td>

                                            <td data-label="Показы" className="num">
                                                {formatNumber(row.impressions)}
                                            </td>
                                            <td data-label="Просмотры" className="num">
                                                {formatNumber(row.views)}
                                            </td>
                                            <td data-label="Контакты" className="num">
                                                {row.unlocks}
                                            </td>

                                            <td data-label="До">
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
                                                            Отправить снова
                                                        </button>
                                                    ) : row.expiring_soon || row.status === 'expired' ? (
                                                        <button
                                                            className="btn btn-primary btn-sm"
                                                            onClick={() =>
                                                                router.post(`/cabinet/listings/${row.id}/renew`, {}, { preserveScroll: true })
                                                            }
                                                        >
                                                            Продлить
                                                        </button>
                                                    ) : row.status === 'active' ? (
                                                        <Link
                                                            href={routes.cabinetPromo}
                                                            className="btn btn-ghost btn-icon"
                                                            aria-label={`Продвинуть «${row.title}»`}
                                                        >
                                                            <Rocket aria-hidden className="size-5" />
                                                        </Link>
                                                    ) : null}

                                                    <Link
                                                        href={routes.listingEdit(row.id)}
                                                        className="btn btn-ghost btn-icon"
                                                        aria-label={`Редактировать «${row.title}»`}
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
