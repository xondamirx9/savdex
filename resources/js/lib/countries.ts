import { t } from '@/lib/i18n';
import { getLocale } from '@/lib/locale';

/** Страна из справочника: код нужен, чтобы знать правила номера компании. */
export interface CountryOption {
    id: number;
    name: string;
    code: string;
}

/** Страны, у которых номер компании проверяется своим правилом (python/savdex/web/tin.py). */
const TIN_COUNTRIES = ['uz', 'cn', 'in', 'kz', 'ru', 'tr'];

/** Какую страну предложить по языку сайта (ТЗ-02): только предложить, не выбрать молча. */
const SUGGESTED: Record<string, string> = { zh: 'cn', tr: 'tr', uz: 'uz', ru: 'uz' };

export function suggestedCountry(countries: CountryOption[]): CountryOption | undefined {
    const code = SUGGESTED[getLocale()];

    return code ? countries.find((c) => c.code === code) : undefined;
}

/** Название поля номера по стране: «ИНН (СТИР)», «统一社会信用代码», «GSTIN или PAN»… */
export function tinLabel(code: string | null | undefined): string {
    return t(`company.tin_by_country.${code && TIN_COUNTRIES.includes(code) ? code : 'other'}`);
}

/** В номере бывают буквы (Китай, Индия) — цифровая клавиатура только для стран из цифр. */
export function tinInputMode(code: string | null | undefined): 'numeric' | 'text' {
    return code === 'cn' || code === 'in' || !code || !TIN_COUNTRIES.includes(code) ? 'text' : 'numeric';
}

export function countryCode(countries: CountryOption[], id: number | null | undefined): string | null {
    return countries.find((c) => c.id === id)?.code ?? null;
}
