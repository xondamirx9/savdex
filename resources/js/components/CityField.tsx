import { SelectField } from '@/components/SelectField';
import { t } from '@/lib/i18n';

/** Пункт «Другой город…»: название пишется текстом (python/savdex/web/city_choice.py). */
export const OTHER_CITY = 'other';

export type CityValue = number | typeof OTHER_CITY | null;

/**
 * Город из справочника выбранной страны и пункт «Другой город…» (ТЗ-02):
 * у страны может не быть нужного города, и раньше его было не указать.
 */
export function CityField({
    id,
    label,
    required = false,
    cities,
    value,
    name,
    onChange,
    onNameChange,
    placeholder,
    error,
    disabled = false,
}: {
    id: string;
    label: string;
    required?: boolean;
    /** Города уже выбранной страны. */
    cities: { id: number; name: string }[];
    value: CityValue;
    name: string;
    onChange: (value: CityValue) => void;
    onNameChange: (name: string) => void;
    placeholder: string;
    error?: string;
    disabled?: boolean;
}) {
    return (
        <div className="field" style={{ margin: 0 }}>
            <label className="label" htmlFor={id}>
                {label}
                {required && <span className="req"> *</span>}
            </label>
            <SelectField
                id={id}
                ariaLabel={label}
                value={value === null ? '' : String(value)}
                disabled={disabled}
                onChange={(next) => onChange(next === OTHER_CITY ? OTHER_CITY : next ? Number(next) : null)}
                placeholder={placeholder}
                options={[
                    ...cities.map((c) => ({ value: String(c.id), label: c.name })),
                    { value: OTHER_CITY, label: t('auth.city_other') },
                ]}
            />
            {value === OTHER_CITY && (
                <input
                    id={`${id}-name`}
                    className="input"
                    style={{ marginTop: 8 }}
                    maxLength={120}
                    value={name}
                    disabled={disabled}
                    aria-label={t('auth.city_other_placeholder')}
                    placeholder={t('auth.city_other_placeholder')}
                    onChange={(e) => onNameChange(e.target.value)}
                    autoFocus
                />
            )}
            {error ? (
                <p className="hint" style={{ color: 'var(--danger)' }}>
                    {error}
                </p>
            ) : (
                value === OTHER_CITY && <p className="hint">{t('auth.city_other_hint')}</p>
            )}
        </div>
    );
}
