/**
 * Переводы интерфейса.
 *
 * Словарь приходит с сервера один раз — при полной загрузке страницы,
 * а не на каждом переходе Inertia: полторы тысячи фраз весят заметно,
 * и гонять их туда-сюда по мобильному интернету незачем. Смена языка
 * — это переход по обычной ссылке с перезагрузкой, и словарь приходит
 * вместе с новой страницей.
 *
 * Ключи именуются по разделу: t('nav.catalog'), t('listing.unlock').
 * Пропущенный ключ возвращается как есть — на экране видно «nav.foo»,
 * и это лучше пустоты: пропуск заметен сразу, а не в проде.
 */

type Dict = Record<string, unknown>;

let dict: Dict = {};
let locale = 'ru';

export function setTranslations(next: Dict, nextLocale: string): void {
    dict = next;
    locale = nextLocale;
}

function lookup(key: string): string | undefined {
    let node: unknown = dict;

    for (const part of key.split('.')) {
        if (typeof node !== 'object' || node === null) return undefined;
        node = (node as Dict)[part];
    }

    return typeof node === 'string' ? node : undefined;
}

/** Подстановка значений: t('found', { count: 12 }) → «Найдено 12». */
function fill(text: string, values?: Record<string, string | number>): string {
    if (!values) return text;

    return Object.entries(values).reduce(
        (acc, [name, value]) => acc.replaceAll(`:${name}`, String(value)),
        text,
    );
}

export function t(key: string, values?: Record<string, string | number>): string {
    return fill(lookup(key) ?? key, values);
}

/**
 * Форма слова при числе.
 *
 * Строка в словаре хранит формы через «|», как это делает Laravel:
 * «объявление|объявления|объявлений». Сколько форм нужно и какую
 * выбрать — зависит от языка: русскому нужны три, английскому две,
 * узбекскому, турецкому и китайскому хватает одной.
 */
export function tChoice(key: string, count: number, values?: Record<string, string | number>): string {
    const forms = (lookup(key) ?? key).split('|');
    const text = forms[index(count, forms.length)] ?? forms[0];

    return fill(text, { count, ...values });
}

function index(count: number, available: number): number {
    if (available === 1) return 0;

    if (locale === 'ru') {
        const n = Math.abs(count) % 100;
        const n1 = n % 10;

        // 11–14 всегда третья форма: одиннадцать объявлений,
        // а не «одиннадцать объявление»
        if (n > 10 && n < 20) return 2;
        if (n1 > 1 && n1 < 5) return 1;
        if (n1 === 1) return 0;

        return 2;
    }

    // Английский различает единственное и множественное; узбекский,
    // турецкий и китайский после числа слово не меняют вовсе
    return count === 1 ? 0 : 1;
}
