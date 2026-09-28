import { ChevronUp, ClipboardList, Plus } from 'lucide-react';
import { useState } from 'react';
import { SelectField } from '@/components/SelectField';
import { t } from '@/lib/i18n';

export interface SpecOption {
    value: string;
    label: string;
}

/** Поле блока «Информация о товаре» — описание приходит с сервера (App\Support\ProductSpecs). */
export interface SpecField {
    key: string;
    label: string;
    type: 'measure' | 'dims' | 'select' | 'number' | 'text';
    units: SpecOption[];
    options: SpecOption[];
    /** Можно ли вписать свой вариант («Другое…») */
    custom: boolean;
}

/** Служебное значение селекта: «вписать свой вариант». */
const OTHER = '__other__';

/*
 * Форматы значения — те же, что проверяет сервер:
 *   мера     «25 kg»         размеры «120x60x75 cm»
 *   выбор    код варианта или свой текст
 */
function splitMeasure(value: string, units: SpecOption[]): [string, string] {
    const [num = '', unit = ''] = value.split(' ');
    return [num, units.some((u) => u.value === unit) ? unit : (units[0]?.value ?? '')];
}

function splitDims(value: string, units: SpecOption[]): [string[], string] {
    const [sizes = '', unit = ''] = value.split(' ');
    const parts = sizes.split('x');
    return [
        [parts[0] ?? '', parts[1] ?? '', parts[2] ?? ''],
        units.some((u) => u.value === unit) ? unit : (units[0]?.value ?? ''),
    ];
}

/** Число без мусора: цифры и одна точка, запятая превращается в точку. */
function num(raw: string): string {
    const v = raw.replace(',', '.').replace(/[^\d.]/g, '');
    const [int, ...rest] = v.split('.');
    return rest.length > 0 ? `${int}.${rest.join('').slice(0, 3)}` : int;
}

function SpecInput({ field, value, onChange }: { field: SpecField; value: string; onChange: (v: string) => void }) {
    // Свой вариант выбран, если значение не совпадает ни с одним кодом
    const [customOpen, setCustomOpen] = useState(
        field.type === 'select' && value !== '' && !field.options.some((o) => o.value === value),
    );
    const id = `spec-${field.key}`;

    if (field.type === 'measure') {
        const [n, unit] = splitMeasure(value, field.units);
        const compose = (nn: string, uu: string) => onChange(nn === '' ? '' : `${nn} ${uu}`);

        return (
            <div className="row" style={{ gap: 8 }}>
                <input
                    id={id}
                    className="input"
                    inputMode="decimal"
                    style={{ flex: 1, minWidth: 0 }}
                    value={n}
                    onChange={(e) => compose(num(e.target.value), unit)}
                    aria-label={`${field.label}: ${t('cabinet.wizard.specs_value')}`}
                />
                {field.units.length > 1 ? (
                    <div style={{ width: 104, flexShrink: 0 }}>
                        <SelectField
                            ariaLabel={`${field.label}: ${t('cabinet.wizard.specs_unit')}`}
                            value={unit}
                            onChange={(u) => compose(n, u)}
                            options={field.units}
                        />
                    </div>
                ) : (
                    <span className="muted t-sm" style={{ alignSelf: 'center', minWidth: 40 }}>
                        {field.units[0]?.label}
                    </span>
                )}
            </div>
        );
    }

    if (field.type === 'dims') {
        const [sizes, unit] = splitDims(value, field.units);
        const labels = [t('cabinet.wizard.specs_length'), t('cabinet.wizard.specs_width'), t('cabinet.wizard.specs_height')];
        const compose = (next: string[], uu: string) =>
            onChange(next.every((p) => p === '') ? '' : `${next.join('x')} ${uu}`);

        return (
            <div className="row" style={{ gap: 6, alignItems: 'center' }}>
                {sizes.map((part, i) => (
                    <input
                        key={i}
                        id={i === 0 ? id : undefined}
                        className="input"
                        inputMode="decimal"
                        style={{ flex: 1, minWidth: 0 }}
                        placeholder={labels[i]}
                        aria-label={`${field.label}: ${labels[i]}`}
                        value={part}
                        onChange={(e) => {
                            const next = [...sizes];
                            next[i] = num(e.target.value);
                            compose(next, unit);
                        }}
                    />
                ))}
                <div style={{ width: 84, flexShrink: 0 }}>
                    <SelectField
                        ariaLabel={`${field.label}: ${t('cabinet.wizard.specs_unit')}`}
                        value={unit}
                        onChange={(u) => compose(sizes, u)}
                        options={field.units}
                    />
                </div>
            </div>
        );
    }

    if (field.type === 'select') {
        const known = field.options.some((o) => o.value === value);

        return (
            <>
                <SelectField
                    id={id}
                    ariaLabel={field.label}
                    value={customOpen ? OTHER : known ? value : ''}
                    onChange={(v) => {
                        if (v === OTHER) {
                            setCustomOpen(true);
                            onChange('');
                        } else {
                            setCustomOpen(false);
                            onChange(v);
                        }
                    }}
                    options={[
                        { value: '', label: t('cabinet.wizard.specs_not_set') },
                        ...field.options,
                        ...(field.custom ? [{ value: OTHER, label: t('cabinet.wizard.specs_other') }] : []),
                    ]}
                />
                {customOpen && (
                    <input
                        className="input mt-8"
                        maxLength={120}
                        value={known ? '' : value}
                        onChange={(e) => onChange(e.target.value)}
                        placeholder={t('cabinet.wizard.specs_other_placeholder')}
                        aria-label={`${field.label}: ${t('cabinet.wizard.specs_other_placeholder')}`}
                    />
                )}
            </>
        );
    }

    return (
        <input
            id={id}
            className="input"
            inputMode={field.type === 'number' ? 'numeric' : undefined}
            maxLength={field.type === 'number' ? 6 : 120}
            value={value}
            onChange={(e) => onChange(field.type === 'number' ? e.target.value.replace(/\D/g, '') : e.target.value)}
        />
    );
}

/**
 * Блок «Информация о товаре» на шаге «Товар и цена».
 *
 * Необязательный: свёрнут, пока ничего не заполнено, — продавец,
 * который не знает деталей, просто идёт дальше. Поля подобраны
 * под категорию сервером; у услуг блока нет вовсе.
 *
 * «Свернуть» только прячет поля, ничего не стирая; стирает «Очистить
 * все». Пустое значение уходит на сервер пустой строкой — так
 * автосохранение удаляет деталь, а не хранит пустоту.
 */
export function ProductSpecsBlock({
    fields,
    values,
    category,
    onChange,
}: {
    fields: SpecField[];
    values: Record<string, string>;
    category: string | null;
    onChange: (next: Record<string, string>) => void;
}) {
    const filled = fields.filter((f) => (values[f.key] ?? '') !== '').length;
    const [open, setOpen] = useState(filled > 0);

    if (fields.length === 0) {
        return null;
    }

    const set = (key: string, value: string) => onChange({ ...values, [key]: value });

    return (
        <section className="card card--pad-sm mt-24" aria-labelledby="specs-title" style={{ background: 'var(--bg)' }}>
            <div className="row" style={{ gap: 10, alignItems: 'center', flexWrap: 'wrap' }}>
                <ClipboardList aria-hidden className="size-5" style={{ color: 'var(--primary-700)' }} />
                <h3 id="specs-title" className="t-h4" style={{ margin: 0 }}>
                    {t('cabinet.wizard.specs_title')}
                </h3>
                <span className="badge">{t('cabinet.wizard.specs_badge')}</span>
                {filled > 0 && (
                    <span className="t-sm muted" style={{ marginLeft: 'auto' }}>
                        {t('cabinet.wizard.specs_filled', { count: filled })}
                    </span>
                )}
            </div>
            <p className="t-sm muted mt-8">
                {category
                    ? t('cabinet.wizard.specs_hint', { category })
                    : t('cabinet.wizard.specs_hint_generic')}
            </p>

            {!open ? (
                <button type="button" className="btn btn-secondary mt-16" onClick={() => setOpen(true)}>
                    <Plus aria-hidden className="size-4" />
                    {t('cabinet.wizard.specs_add')}
                </button>
            ) : (
                <>
                    <div className="grid grid-2 grid-tight mt-16" style={{ gap: 14 }}>
                        {fields.map((f) => (
                            <div
                                key={f.key}
                                className="field"
                                style={{ margin: 0, gridColumn: f.type === 'dims' ? '1 / -1' : undefined }}
                            >
                                <label className="label" htmlFor={`spec-${f.key}`}>
                                    {f.label}
                                </label>
                                <SpecInput field={f} value={values[f.key] ?? ''} onChange={(v) => set(f.key, v)} />
                            </div>
                        ))}
                    </div>
                    <div className="row mt-16" style={{ gap: 8, flexWrap: 'wrap' }}>
                        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setOpen(false)}>
                            <ChevronUp aria-hidden className="size-4" />
                            {t('cabinet.wizard.specs_collapse')}
                        </button>
                        {filled > 0 && (
                            <button
                                type="button"
                                className="btn btn-ghost btn-sm"
                                onClick={() =>
                                    onChange({
                                        ...values,
                                        ...Object.fromEntries(fields.map((f) => [f.key, ''])),
                                    })
                                }
                            >
                                {t('cabinet.wizard.specs_clear')}
                            </button>
                        )}
                    </div>
                </>
            )}
        </section>
    );
}
