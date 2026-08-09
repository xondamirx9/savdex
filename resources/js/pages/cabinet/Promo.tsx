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
import { pluralize } from '@/lib/plural';

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
            title="Продвижение"
            heading="Продвижение"
            subheading={
                <>
                    {pluralize(units, ['единица', 'единицы', 'единиц'])} продвижения на счёте
                    {resets_at && ` · обновится ${resets_at}`}
                </>
            }
        >
            {listings.length === 0 && (
                <div className="alert alert-warning" style={{ marginBottom: 24 }}>
                    <Info aria-hidden className="size-5" />
                    <div>Продвигать пока нечего: нужно хотя бы одно активное объявление.</div>
                </div>
            )}

            <Panel title="Активные продвижения" className="mb-24">
                {active.length === 0 ? (
                    <p className="muted t-sm">
                        Сейчас ничего не продвигается. Инструменты ниже поднимают объявление в выдаче — эффект виден
                        в этой таблице.
                    </p>
                ) : (
                    <div className="table-wrap table-cards" style={{ border: 'none' }}>
                        <table className="table" style={{ minWidth: 0 }}>
                            <thead>
                                <tr>
                                    <th>Объявление</th>
                                    <th>Инструмент</th>
                                    <th>До</th>
                                    <th className="num">Показы до</th>
                                    <th className="num">Показы после</th>
                                    <th className="num">Эффект</th>
                                </tr>
                            </thead>
                            <tbody>
                                {active.map((p) => (
                                    <tr key={p.id}>
                                        <td data-label="Объявление">
                                            <b>{p.listing}</b>
                                        </td>
                                        <td data-label="Инструмент">
                                            <span className="badge badge-top">{p.badge ?? p.type}</span>
                                        </td>
                                        <td data-label="До">{p.ends_at ?? 'разово'}</td>
                                        <td data-label="Показы до" className="num">
                                            {formatNumber(p.before)}
                                        </td>
                                        <td data-label="Показы после" className="num">
                                            {p.after !== null ? formatNumber(p.after) : '—'}
                                        </td>
                                        <td
                                            data-label="Эффект"
                                            className="num"
                                            style={{ color: (p.effect ?? 0) > 0 ? 'var(--success)' : undefined }}
                                        >
                                            {/* Промежуточный эффект не показываем: цифра
                                                до окончания периода вводит в заблуждение */}
                                            {p.effect !== null ? `${p.effect > 0 ? '+' : ''}${p.effect} %` : 'считаем'}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>
                )}
            </Panel>

            <h2 className="t-h3" style={{ marginBottom: 16 }}>
                Купить продвижение
            </h2>

            <div className="grid grid-3">
                {types.map((t) => {
                    const Icon = ICONS[t.icon ?? ''] ?? Rocket;
                    const enough = units >= t.cost;
                    const disabled = !t.available || !enough || listings.length === 0;

                    return (
                        <div
                            key={t.id}
                            className={cn('card card-hover')}
                            style={t.code === 'category_top' ? { borderColor: 'var(--primary-500)' } : undefined}
                        >
                            <div className="row-between" style={{ marginBottom: 10 }}>
                                <span
                                    className={cn('ico-box', t.code === 'category_top' && 'ico-box-solid')}
                                >
                                    <Icon aria-hidden className="size-5" />
                                </span>
                                <b>{t.cost_label}</b>
                            </div>

                            <h3 className="t-h4">{t.name}</h3>
                            <p className="t-sm muted mt-8">{t.description}</p>
                            {t.effect_hint && (
                                <p className="t-sm mt-16" style={{ color: 'var(--success)' }}>
                                    {t.effect_hint}
                                </p>
                            )}

                            {t.slots !== null && (
                                <p className="t-caption muted mt-8">
                                    {t.available
                                        ? `Свободно ${pluralize(t.slots - (t.taken ?? 0), ['место', 'места', 'мест'])} из ${t.slots}`
                                        : `Занято ${t.taken} из ${t.slots} — места освободятся после окончания размещений`}
                                </p>
                            )}

                            {!enough && (
                                <p className="t-caption mt-8" style={{ color: 'var(--warning)' }}>
                                    Не хватает единиц: нужно {t.cost}, есть {units}
                                </p>
                            )}

                            <button
                                className={cn('btn btn-block mt-16', t.code === 'category_top' ? 'btn-primary' : 'btn-outline')}
                                disabled={disabled}
                                onClick={() => apply(t)}
                            >
                                {t.available ? 'Применить' : 'Мест нет'}
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
                title={picking ? `Запустить «${picking.name}»` : ''}
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
                                ? 'Запускаем…'
                                : `Подтвердить и списать ${pluralize(picking?.cost ?? 0, ['единицу', 'единицы', 'единиц'])}`}
                        </button>
                        <button className="btn btn-ghost" onClick={() => setPicking(null)}>
                            Отмена
                        </button>
                    </>
                }
            >
                {picking && (
                    <>
                        <div className="field">
                            <label className="label" htmlFor="promo-listing">
                                Какое объявление продвигаем <span className="req">*</span>
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
                                <span className="muted">Стоимость</span>
                                <b>{pluralize(picking.cost, ['единица', 'единицы', 'единиц'])}</b>
                            </div>
                            <div className="row-between t-sm" style={{ marginBottom: 8 }}>
                                <span className="muted">Срок действия</span>
                                <b>{picking.cost_label.includes('/') ? picking.cost_label.split('/')[1].trim() : 'разово'}</b>
                            </div>
                            <div className="row-between t-sm">
                                <span className="muted">Останется на счёте</span>
                                <b>{units - picking.cost}</b>
                            </div>
                        </div>

                        {picking.effect_hint && (
                            <p className="t-sm mt-16" style={{ color: 'var(--success)' }}>
                                {picking.effect_hint}
                            </p>
                        )}

                        <p className="t-caption muted mt-8">
                            Единицы спишутся сразу, продвижение начнёт действовать в течение нескольких минут.
                            Отменить запуск и вернуть единицы нельзя.
                        </p>
                    </>
                )}
            </Modal>

            <div className="alert alert-info mt-24">
                <Info aria-hidden className="size-5" />
                <div>
                    Продвинутые объявления помечаются словом «Продвигается». Мы не выдаём рекламу за органическую
                    выдачу — это принцип площадки.
                </div>
            </div>
        </CabinetLayout>
    );
}
