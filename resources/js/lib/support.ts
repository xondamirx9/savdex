import { usePage } from '@inertiajs/react';
import type { SharedProps, SupportContacts } from '@/types';

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
    const { support } = usePage<SharedProps>().props;

    return {
        ...support,
        telHref: 'tel:' + support.phone.replace(/[^+\d]/g, ''),
        tgHandle: '@' + (support.telegram.split('/').filter(Boolean).pop() ?? ''),
    };
}
