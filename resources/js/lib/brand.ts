import { usePage } from '@inertiajs/react';

import type { SharedProps } from '@/types';

/** Знак из репозитория: он же стоит, пока свой не загрузили. */
const FALLBACK = '/images/logo-mark.svg';

/**
 * Адрес логотипа площадки из настроек админки.
 *
 * Запасной адрес держим здесь, а не в каждом месте вывода: шапка,
 * подвал и экраны входа рисуют один и тот же знак, и три разных
 * умолчания рано или поздно разъедутся.
 */
export function useBrandLogo(): { src: string; custom: boolean } {
    const src = usePage<SharedProps>().props.brandLogo;

    /*
     * custom нужен вёрстке: над первым экраном шапка выбеливает знак
     * фильтром — знак из коробки одноцветный, и на тёмном баннере
     * иначе не читается. Чужой логотип так превратился бы в белое
     * пятно, поэтому ему фильтр не достаётся.
     */
    return { src: src || FALLBACK, custom: Boolean(src) && src !== FALLBACK };
}
