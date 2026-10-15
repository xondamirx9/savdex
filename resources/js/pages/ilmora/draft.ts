import type { IlmoraForm } from './rules';

/**
 * Черновик анкеты ILMORA в sessionStorage этой вкладки: человек уходит
 * читать договор (/ilmora/contract) и возвращается к заполненной форме, а
 * страница договора берёт из черновика ФИО для строки «Я, <ФИО>, …».
 *
 * sessionStorage, а не localStorage: черновик с ПИНФЛ живёт, пока открыта
 * вкладка, и не остаётся на чужом компьютере. После отправки — стирается.
 * Хранилище бывает недоступно (приватный режим, запрет) — тогда тихо без него.
 */

const KEY = 'ilmora.draft';

export function loadDraft(): Partial<IlmoraForm> | null {
    try {
        const raw = window.sessionStorage.getItem(KEY);
        const data: unknown = raw ? JSON.parse(raw) : null;

        return data && typeof data === 'object' ? (data as Partial<IlmoraForm>) : null;
    } catch {
        return null;
    }
}

export function saveDraft(data: IlmoraForm): void {
    try {
        window.sessionStorage.setItem(KEY, JSON.stringify(data));
    } catch {
        // Нет хранилища — форма просто не переживёт переход
    }
}

export function clearDraft(): void {
    try {
        window.sessionStorage.removeItem(KEY);
    } catch {
        // То же
    }
}

/** ФИО из черновика — для страницы договора; нет — пусто */
export function draftName(): string {
    const name = loadDraft()?.full_name;

    return typeof name === 'string' ? name.trim().split(/\s+/).filter(Boolean).join(' ') : '';
}
