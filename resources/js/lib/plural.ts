/**
 * Склонение существительного после числа.
 *
 * Русский требует три формы: 1 место, 2 места, 5 мест. Подставлять
 * одну и ту же («2 мест») — заметная небрежность: её видят даже те,
 * кто не читает текст внимательно.
 *
 * @param forms [одно, два, пять] — «место», «места», «мест»
 */
export function plural(count: number, forms: [string, string, string]): string {
    const n = Math.abs(count) % 100;
    const n1 = n % 10;

    // 11–14 всегда третья форма: одиннадцать мест, а не «одиннадцать место»
    if (n > 10 && n < 20) return forms[2];
    if (n1 > 1 && n1 < 5) return forms[1];
    if (n1 === 1) return forms[0];

    return forms[2];
}

/** Число вместе со склонённым словом: «3 объявления». */
export function pluralize(count: number, forms: [string, string, string]): string {
    return `${count} ${plural(count, forms)}`;
}
