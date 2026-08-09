/**
 * Язык в адресе.
 *
 * Сервер снимает префикс до маршрутизации, поэтому пути в routes.ts
 * записаны без языка — «/catalog», а не «/uz/catalog». Префикс
 * добавляется здесь, в момент перехода и при отрисовке ссылки.
 *
 * Так сделано ради одного: ссылки в разметке узбекской страницы
 * должны вести на узбекские страницы. Иначе весь нерусский раздел
 * остаётся без внутренних ссылок — поисковик знает о нём только
 * из карты сайта и по одной этой причине считает второстепенным.
 */

/** Языки, у которых есть префикс. Русский живёт без него. */
export const PREFIXED = ['uz', 'en', 'zh', 'tr'] as const;

export const DEFAULT_LOCALE = 'ru';

/**
 * Текущий язык.
 *
 * Модульная переменная, а не контекст: адрес нужен и вне дерева
 * компонентов — в обработчике переходов Inertia, куда хук не достаёт.
 */
let current: string = DEFAULT_LOCALE;

export function setLocale(locale: string): void {
    current = locale;
}

export function getLocale(): string {
    return current;
}

/** Отделить язык от пути: «/uz/catalog» → ['uz', '/catalog']. */
export function splitLocale(path: string): [string | null, string] {
    for (const code of PREFIXED) {
        if (path === `/${code}`) return [code, '/'];
        if (path.startsWith(`/${code}/`)) return [code, path.slice(code.length + 1)];
    }

    return [null, path];
}

/** Убрать язык из пути — нужно для сравнения с routes.* */
export function stripLocale(path: string): string {
    return splitLocale(path)[1];
}

/**
 * Добавить в путь текущий язык.
 *
 * Внешние адреса и якоря не трогаем: «/uz/mailto:…» и «/uz/#top»
 * никуда не ведут.
 */
export function localize(path: string, locale: string = current): string {
    if (!path.startsWith('/') || path.startsWith('//')) return path;

    const [, clean] = splitLocale(path);

    if (locale === DEFAULT_LOCALE) return clean;

    // «/uz/» с пустым хвостом — это главная, и слэш на конце лишний
    return clean === '/' ? `/${locale}` : `/${locale}${clean}`;
}
