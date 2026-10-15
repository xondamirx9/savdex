import type { IlmoraForm } from './rules';

/**
 * Черновик анкеты ILMORA в sessionStorage этой вкладки: человек уходит
 * читать оферту (/ilmora/offer) и возвращается к заполненной форме, а
 * страница оферты заполняет из черновика пустые места заявления.
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
