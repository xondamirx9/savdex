import { router } from '@inertiajs/react';
import type { AnalyticsProps, SharedProps } from '@/types';

/**
 * Google Analytics 4 (ТЗ-03) — одно место на весь сайт: сменить
 * инструмент — значит поправить этот файл, а не страницы.
 *
 * Тег ставит сервер (savdex/web/analytics.py) только на боевом сайте;
 * без него window.gtag нет, и track() молча ничего не делает — на
 * локальном запуске и в проверках события никуда не уходят.
 *
 * Персональных данных в событиях нет: почта, телефон, ИНН, имя и
 * название компании сюда не передаются — только коды и признаки.
 */

type Params = Record<string, string | number | boolean | null | undefined>;

declare global {
    interface Window {
        gtag?: (...args: unknown[]) => void;
    }
}

export function track(name: string, params: Params = {}): void {
    if (typeof window === 'undefined' || typeof window.gtag !== 'function') return;

    window.gtag('event', name, params);
}

/**
 * Дождаться, пока Inertia обновит <head> новой страницы: заголовок
 * вкладки она ставит после отрисовки, и page_view с прошлым заголовком
 * записал бы переход не туда. Не дольше 300 мс — у страниц с тем же
 * заголовком <head> может и не поменяться.
 */
function afterHead(send: () => void): void {
    let done = false;
    const fire = () => {
        if (done) return;
        done = true;
        observer.disconnect();
        window.clearTimeout(timer);
        // Все теги одной пачкой — читать заголовок после неё
        window.setTimeout(send, 0);
    };
    const observer = new MutationObserver(fire);
    observer.observe(document.head, { childList: true, subtree: true, characterData: true });
    const timer = window.setTimeout(fire, 300);
}

/**
 * Просмотры страниц и события сервера.
 *
 * Inertia меняет страницы без перезагрузки, поэтому page_view
 * отправляется здесь на каждый переход — включая первую страницу:
 * тег настроен с send_page_view: false, чтобы её не считать дважды.
 * У первой страницы заголовок уже пришёл с сервера — она уходит сразу.
 */
export function startAnalytics(): void {
    if (typeof window === 'undefined') return;

    let first = true;

    router.on('navigate', (event) => {
        const props = event.detail.page.props as { analytics?: AnalyticsProps; locale?: string };
        const analytics = props.analytics;
        const initial = first;
        first = false;

        if (!analytics?.id || window.location.pathname.startsWith('/admin')) return;

        (initial ? (send: () => void) => send() : afterHead)(() => {
            window.gtag?.('set', {
                user_properties: { plan: analytics.plan ?? 'guest', locale: props.locale ?? 'ru' },
            });
            track('page_view', {
                page_location: window.location.href,
                page_title: document.title,
                language: props.locale ?? 'ru',
            });

            for (const e of analytics.events) track(e.name, e.params);
        });
    });
}


/**
 * С чем человек нажал «Открыть контакты»: гость, без компании, с
 * неподтверждённой почтой или всё готово — воронка открытия контактов.
 */
export function unlockState(auth: SharedProps['auth'] | undefined): string {
    if (!auth?.user) return 'guest';
    if (!auth.company) return 'no_company';
    if (!auth.user.email_verified) return 'email_unverified';

    return 'ok';
}
