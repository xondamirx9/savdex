/**
 * Флаг страны из двухбуквенного кода ISO.
 *
 * Эмодзи, а не картинки: флаг собирается из двух символов-индикаторов
 * региона (U+1F1E6…U+1F1FF), рисуется шрифтом системы и не требует
 * ни спрайта, ни запросов. Неизвестный или пустой код возвращает
 * пустую строку — карточка просто не рисует флаг.
 */
export function flag(code: string | null | undefined): string {
    if (!code || code.length !== 2 || !/^[a-zA-Z]{2}$/.test(code)) return '';

    const base = 0x1f1e6 - 65; // 'A' → региональный индикатор A

    return String.fromCodePoint(
        ...code.toUpperCase().split('').map((c) => base + c.charCodeAt(0)),
    );
}
