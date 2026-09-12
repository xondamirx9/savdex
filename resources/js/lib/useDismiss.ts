import { useEffect, useRef } from 'react';

/**
 * Закрывает выпадающий блок при клике снаружи и по Escape.
 *
 * Лежит отдельно от шапки: тем же поведением пользуются выпадающие
 * списки на обычных страницах, а тянуть ради него весь SiteHeader
 * в страницу значит тащить и меню, и поиск, и счётчики сообщений.
 */
export function useDismiss(onDismiss: () => void) {
    const ref = useRef<HTMLDivElement>(null);

    useEffect(() => {
        const onClick = (e: MouseEvent) => {
            if (ref.current && !ref.current.contains(e.target as Node)) onDismiss();
        };
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onDismiss();
        };
        document.addEventListener('click', onClick);
        document.addEventListener('keydown', onKey);
        return () => {
            document.removeEventListener('click', onClick);
            document.removeEventListener('keydown', onKey);
        };
    }, [onDismiss]);

    return ref;
}
