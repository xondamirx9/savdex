import { usePage } from '@inertiajs/react';
import type { SharedProps, SupportContacts } from '@/types';

const EMPTY: SupportContacts = {
    email: '',
    phone: '',
    hours: '',
    telegram: '',
    legal_name: '',
    legal_tin: '',
};

/**
 * Контакты поддержки из настроек админки — с готовыми производными
 * для вёрстки: адресом tel:-ссылки и телеграм-ником с собакой.
 *
 * Производные считаются здесь, а не в каждой странице: телефон
 * с пробелами и дефисами в href не работает, а резать ссылку
 * https://t.me/… до ника в трёх местах по-разному — верный способ
 * получить три разных результата.
 */
export function useSupport(): SupportContacts & { telHref: string; tgHandle: string } {
    /*
     * Страница ошибки может прийти без общих пропсов (посредник Inertia
     * не запускается, когда маршрут не совпал) — тогда support нет,
     * и обращение к его полям уронило бы страницу в белый экран.
     */
    const props = usePage<SharedProps>().props as Partial<SharedProps> | undefined;
    const support: SupportContacts = { ...EMPTY, ...(props?.support ?? {}) };
    const phone = support.phone ?? '';
    const handle = (support.telegram ?? '').split('/').filter(Boolean).pop() ?? '';

    return {
        ...support,
        telHref: phone ? 'tel:' + phone.replace(/[^+\d]/g, '') : '',
        tgHandle: handle ? '@' + handle : '',
    };
}
