import { useForm } from '@inertiajs/react';
import {
    ArrowUp,
    Clock,
    Grid3x3,
    Home,
    Info,
    Mail,
    Rocket,
    Star,
} from 'lucide-react';
import type { ComponentType } from 'react';
import { useState } from 'react';
import { Modal } from '@/components/Modal';
import { Panel, formatNumber } from '@/components/cabinet';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { cn } from '@/lib/cn';
import { t, tChoice } from '@/lib/i18n';

interface Type {
    id: number;
    code: string;
    name: string;
    description: string;
    effect_hint: string | null;
    cost: number;
    cost_label: string;
    icon: string | null;
    slots: number | null;
    taken: number | null;
    available: boolean;
}

interface Active {
    id: number;
    listing: string | null;
    type: string | null;
    badge: string | null;
    ends_at: string | null;
    before: number;
    after: number | null;
    effect: number | null;
}

const ICONS: Record<string, ComponentType<{ className?: string; 'aria-hidden'?: boolean }>> = {
    'arrow-up': ArrowUp,
    star: Star,
    clock: Clock,
    grid: Grid3x3,
    home: Home,
    mail: Mail,
};

export default function Promo({
    active,
    types,
    listings,
    units,
    resets_at,
}: {
    active: Active[];
    types: Type[];
    listings: { id: number; title: string }[];
    units: number;
    resets_at: string | null;
}) {
    const [picking, setPicking] = useState<Type | null>(null);
    const form = useForm({ listing_id: listings[0]?.id ?? 0, promotion_type_id: 0 });

    function apply(type: Type) {
        // Продвигать нечего — сначала нужно активное объявление
        if (listings.length === 0) return;

        setPicking(type);
        form.setData({ listing_id: listings[0].id, promotion_type_id: type.id });
    }

    function submit() {
        form.post('/cabinet/promo', { preserveScroll: true, onSuccess: () => setPicking(null) });
    }

    return (
        <CabinetLayout
            title={t('cabinet.promo.title')}
            heading={t('cabinet.promo.title')}
            subheading={
                <>
                    {tChoice('cabinet.promo.balance', units)}
                    {resets_at && ` · ${t('cabinet.promo.resets', { date: resets_at })}`}
                </>
            }
        >
            {listings.length === 0 && (
                <div className="alert alert-warning" style={{ marginBottom: 24 }}>
                    <Info aria-hidden className="size-5" />
                    <div>{t('cabinet.promo.nothing_to_promote')}</div>
                </div>
            )}

            <Panel title={t('cabinet.promo.active')} className="mb-24">
                {active.length === 0 ? (
                    <p className="muted t-sm">{t('cabinet.promo.active_empty')}</p>
                ) : (
                    <div className="table-wrap table-cards" style={{ border: 'none' }}>
                        <table className="table" style={{ minWidth: 0 }}>
                            <thead>
                                <tr>
                                    <th>{t('cabinet.promo.col_listing')}</th>
                                    <th>{t('cabinet.promo.col_tool')}</th>
                                    <th>{t('cabinet.promo.col_until')}</th>
                                    <th className="num">{t('cabinet.promo.col_before')}</th>
                                    <th className="num">{t('cabinet.promo.col_after')}</th>
                                    <th className="num">{t('cabinet.promo.col_effect')}</th>
                                </tr>
                            </thead>
                            <tbody>
                                {active.map((p) => (
                                    <tr key={p.id}>
                                        <td data-label={t('cabinet.promo.col_listing')}>
                                            <b>{p.listing}</b>
                                        </td>
                                        <td data-label={t('cabinet.promo.col_tool')}>
                                            <span className="badge badge-top">{p.badge ?? p.type}</span>
                                        </td>
                                        <td data-label={t('cabinet.promo.col_until')}>
                                            {p.ends_at ?? t('cabinet.promo.once')}
                                        </td>
                                        <td data-label={t('cabinet.promo.col_before')} className="num">
                                            {formatNumber(p.before)}
                                        </td>
                                        <td data-label={t('cabinet.promo.col_after')} className="num">
                                            {p.after !== null ? formatNumber(p.after) : '—'}
                                        </td>
                                        <td
                                            data-label={t('cabinet.promo.col_effect')}
                                            className="num"
                                            style={{ color: (p.effect ?? 0) > 0 ? 'var(--success)' : undefined }}
                                        >
                                            {/* Промежуточный эффект не показываем: цифра
                                                до окончания периода вводит в заблуждение */}
                                            {p.effect !== null
                                                ? `${p.effect > 0 ? '+' : ''}${p.effect} %`
                                                : t('cabinet.promo.counting')}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </Panel>

            <h2 className="t-h3" style={{ marginBottom: 16 }}>
                {t('cabinet.promo.buy')}
            </h2>

            <div className="grid grid-3">
                {types.map((item) => {
                    const Icon = ICONS[item.icon ?? ''] ?? Rocket;
                    const enough = units >= item.cost;
                    const disabled = !item.available || !enough || listings.length === 0;

                    return (
                        <div
                            key={item.id}
                            className={cn('card card-hover')}
                            style={item.code === 'category_top' ? { borderColor: 'var(--primary-500)' } : undefined}
                        >
                            <div className="row-between" style={{ marginBottom: 10 }}>
                                <span
                                    className={cn('ico-box', item.code === 'category_top' && 'ico-box-solid')}
                                >
                                    <Icon aria-hidden className="size-5" />
                                </span>
                                <b>{item.cost_label}</b>
                            </div>

                            <h3 className="t-h4">{item.name}</h3>
                            <p className="t-sm muted mt-8">{item.description}</p>
                            {item.effect_hint && (
                                <p className="t-sm mt-16" style={{ color: 'var(--success)' }}>
                                    {item.effect_hint}
                                </p>
                            )}

                            {item.slots !== null && (
                                <p className="t-caption muted mt-8">
                                    {item.available
                                        ? tChoice('cabinet.promo.slots_free', item.slots - (item.taken ?? 0), {
                                              total: item.slots,
                                          })
                                        : t('cabinet.promo.slots_taken', {
                                              taken: item.taken ?? 0,
                                              total: item.slots,
                                          })}
                                </p>
                            )}

                            {!enough && (
                                <p className="t-caption mt-8" style={{ color: 'var(--warning)' }}>
                                    {t('cabinet.promo.not_enough', { need: item.cost, have: units })}
                                </p>
                            )}

                            <button
                                className={cn('btn btn-block mt-16', item.code === 'category_top' ? 'btn-primary' : 'btn-outline')}
                                disabled={disabled}
                                onClick={() => apply(item)}
                            >
                                {item.available ? t('cabinet.promo.apply') : t('cabinet.promo.no_slots')}
                            </button>
                        </div>
                    );
                })}
            </div>

            {/*
                Подтверждение — модальное окно, а не блок внизу страницы.
                Раньше форма появлялась ниже сгиба: человек нажимал
                «Применить», ничего не происходило на экране, и кнопка
                читалась как нерабочая.
            */}
            <Modal
                open={picking !== null}
                onClose={() => setPicking(null)}
                title={picking ? t('cabinet.promo.start', { name: picking.name }) : ''}
                description={picking?.description}
                width={520}
                footer={
                    <>
                        <button
                            className="btn btn-primary"
                            style={{ flex: 1 }}
                            disabled={form.processing}
                            onClick={submit}
                        >
                            {form.processing
                                ? t('cabinet.promo.starting')
                                : tChoice('cabinet.promo.confirm', picking?.cost ?? 0)}
                        </button>
                        <button className="btn btn-ghost" onClick={() => setPicking(null)}>
                            {t('common.cancel')}
                        </button>
                    </>
                }
            >
                {picking && (
                    <>
                        <div className="field">
                            <label className="label" htmlFor="promo-listing">
                                {t('cabinet.promo.which_listing')} <span className="req">*</span>
                            </label>
                            <select
                                id="promo-listing"
                                className="select"
                                value={form.data.listing_id}
                                onChange={(e) => form.setData('listing_id', Number(e.target.value))}
                            >
                                {listings.map((l) => (
                                    <option key={l.id} value={l.id}>
                                        {l.title}
                                    </option>
                                ))}
                            </select>
                            {form.errors.listing_id && (
                                <p className="hint" style={{ color: 'var(--danger)' }}>
                                    {form.errors.listing_id}
                                </p>
                            )}
                        </div>

                        {/* Что именно списывается и что останется — до нажатия,
                            а не после: списание единиц необратимо */}
                        <div className="card card--pad-sm" style={{ background: 'var(--bg)', border: 'none' }}>
                            <div className="row-between t-sm" style={{ marginBottom: 8 }}>
                                <span className="muted">{t('cabinet.promo.cost')}</span>
                                <b>{tChoice('cabinet.promo.units', picking.cost)}</b>
                            </div>
                            <div className="row-between t-sm" style={{ marginBottom: 8 }}>
                                <span className="muted">{t('cabinet.promo.duration')}</span>
                                <b>
                                    {picking.cost_label.includes('/')
                                        ? picking.cost_label.split('/')[1].trim()
                                        : t('cabinet.promo.once')}
                                </b>
                            </div>
                            <div className="row-between t-sm">
                                <span className="muted">{t('cabinet.promo.left')}</span>
                                <b>{units - picking.cost}</b>
                            </div>
                        </div>

                        {picking.effect_hint && (
                            <p className="t-sm mt-16" style={{ color: 'var(--success)' }}>
                                {picking.effect_hint}
                            </p>
                        )}

                        <p className="t-caption muted mt-8">{t('cabinet.promo.irreversible')}</p>
                    </>
                )}
            </Modal>

            <div className="alert alert-info mt-24">
                <Info aria-hidden className="size-5" />
                <div>{t('cabinet.promo.honest')}</div>
            </div>
        </CabinetLayout>
    );
}
