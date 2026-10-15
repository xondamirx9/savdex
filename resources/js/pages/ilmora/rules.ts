import { t } from '@/lib/i18n';

/**
 * Проверка формы ILMORA в браузере — сразу, под полем. Те же правила и
 * тексты, что на сервере (python/savdex/ilmora/form.py); решает сервер,
 * здесь — только чтобы человек не ждал ответа ради опечатки.
 */

export type IlmoraForm = {
    phone: string;
    full_name: string;
    person_type: '' | 'individual' | 'legal';
    pinfl: string;
    tin: string;
    offer_read: boolean;
    offer_sign: boolean;
};

export type IlmoraErrors = Partial<Record<keyof IlmoraForm, string>>;

const LETTER = 'A-Za-zÀ-ɏЀ-ӿ';
const APOSTROPHES = "'ʻʼ‘’";
/** Слово ФИО: с буквы; апостроф где угодно после неё, дефис — только перед буквой */
const WORD = new RegExp(`^[${LETTER}](?:[${LETTER}${APOSTROPHES}]|-(?=[${LETTER}]))*$`);
const MAX_NAME = 150;

export const PHONE_DIGITS = 9;
export const PINFL_DIGITS = 14;
export const TIN_DIGITS = 9;

/** ФИО: пробелы по краям обрезаны, между словами — по одному */
export function cleanName(value: string): string {
    return value.normalize('NFC').trim().split(/\s+/).filter(Boolean).join(' ');
}

/**
 * Цифры номера телефона после +998 — то, что уходит на сервер. Вставили
 * номер целиком («+998 99 222 33 44») — код страны отрезается.
 */
export function phoneDigits(value: string): string {
    const digits = value.replace(/\D/g, '');

    return (digits.length > PHONE_DIGITS && digits.startsWith('998') ? digits.slice(3) : digits).slice(
        0,
        PHONE_DIGITS,
    );
}

/** Маска «99 222 33 44» */
export function formatPhone(digits: string): string {
    const parts = [digits.slice(0, 2), digits.slice(2, 5), digits.slice(5, 7), digits.slice(7, 9)];

    return parts.filter(Boolean).join(' ');
}

function digitsError(field: 'phone' | 'pinfl' | 'tin', value: string, length: number): string | undefined {
    const clean = value.replace(/[\s-]/g, '');

    if (clean === '') return t(`ilmora.errors.${field}_required`);
    if (!/^\d+$/.test(clean)) return t(`ilmora.errors.${field}_digits`);
    if (clean.length !== length) return t(`ilmora.errors.${field}_length`, { count: clean.length });

    return undefined;
}

function nameError(value: string): string | undefined {
    const name = cleanName(value);

    if (name === '') return t('ilmora.errors.name_required');
    if (name.length > MAX_NAME) return t('ilmora.errors.name_long', { max: MAX_NAME });

    const words = name.split(' ');

    if (words.some((word) => !WORD.test(word))) return t('ilmora.errors.name_letters');
    if (words.length < 3) return t('ilmora.errors.name_words');

    return undefined;
}

function pinflError(value: string): string | undefined {
    const problem = digitsError('pinfl', value, PINFL_DIGITS);

    if (problem) return problem;

    // Одна цифра 14 раз — как правило регистрации Savdex (auth_actions._pinfl)
    return /^(\d)\1+$/.test(value.replace(/[\s-]/g, '')) ? t('messages.register.pinfl_invalid') : undefined;
}

/** Ошибки по полям; пусто — форму можно отправлять */
export function validateIlmora(data: IlmoraForm): IlmoraErrors {
    const errors: IlmoraErrors = {};
    const put = (field: keyof IlmoraForm, message: string | undefined) => {
        if (message) errors[field] = message;
    };

    put('phone', digitsError('phone', data.phone, PHONE_DIGITS));
    put('full_name', nameError(data.full_name));

    if (data.person_type === '') put('person_type', t('ilmora.errors.person_type'));
    if (data.person_type === 'individual') put('pinfl', pinflError(data.pinfl));
    if (data.person_type === 'legal') put('tin', digitsError('tin', data.tin, TIN_DIGITS));

    if (!data.offer_read) put('offer_read', t('ilmora.errors.offer_read'));
    if (!data.offer_sign) put('offer_sign', t('ilmora.errors.offer_sign'));

    return errors;
}
