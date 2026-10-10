import { SelectField } from '@/components/SelectField';
import { suggestedCountry, type CountryOption } from '@/lib/countries';
import { t } from '@/lib/i18n';

/**
 * Страна компании (ТЗ-02): обязательная и без значения по умолчанию.
 * Молча подставленный Узбекистан записал китайскую компанию в Ташкент,
 * а её 18-значный код пришлось обрезать до 9 цифр узбекского ИНН. По языку
 * сайта страна только предлагается кнопкой — выбирает человек.
 */
export function CountryField({
    id,
    countries,
    value,
    onChange,
    error,
    hint,
}: {
    id: string;
    countries: CountryOption[];
    value: number | null;
    onChange: (id: number | null) => void;
    error?: string;
    hint?: string;
}) {
    const suggestion = value === null ? suggestedCountry(countries) : undefined;

    return (
        <div className="field" style={{ margin: 0 }}>
            <label className="label" htmlFor={id}>
                {t('auth.country_label')} <span className="req">*</span>
            </label>
            <SelectField
                id={id}
                ariaLabel={t('auth.country_label')}
                value={value === null ? '' : String(value)}
                onChange={(next) => onChange(next ? Number(next) : null)}
                placeholder={t('auth.country_placeholder')}
                options={countries.map((c) => ({ value: String(c.id), label: c.name }))}
            />
            {suggestion && (
                <button
                    type="button"
                    className="chip"
                    style={{ marginTop: 6 }}
                    onClick={() => onChange(suggestion.id)}
                >
                    {t('auth.country_suggest', { country: suggestion.name })}
                </button>
            )}
            {error ? (
                <p className="hint" style={{ color: 'var(--danger)' }}>
                    {error}
                </p>
            ) : (
                hint && <p className="hint">{hint}</p>
            )}
        </div>
    );
}
