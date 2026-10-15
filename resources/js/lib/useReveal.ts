import { useEffect } from 'react';

/**
 * Появление блоков при прокрутке.
 *
 * Один наблюдатель на всю страницу вместо наблюдателя на каждый блок:
 * при полусотне карточек разница заметна. Элемент отписывается сразу
 * после появления — повторно анимировать при обратной прокрутке не нужно,
 * это раздражает.
 *
 * Работает через data-атрибуты, а не обёртку-компонент: не добавляет
 * лишних узлов в DOM и не ломает гриды.
 */
export function useReveal(deps: unknown[] = []) {
    useEffect(() => {
        const targets = document.querySelectorAll<HTMLElement>('[data-reveal], [data-reveal-stagger]');
        if (targets.length === 0) return;

        // Уважаем системную настройку: показываем всё сразу
        if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            targets.forEach((el) => el.classList.add('is-visible'));
            return;
        }

        // Что наблюдаем → какие элементы показать, когда оно появилось
        const watched = new Map<Element, HTMLElement[]>();
        const io = new IntersectionObserver(
            (entries) => {
                entries.forEach((entry) => {
                    if (!entry.isIntersecting) return;
                    (watched.get(entry.target) ?? []).forEach((el) => el.classList.add('is-visible'));
                    io.unobserve(entry.target);
                });
            },
            // Запускаем чуть раньше, чем блок доедет до края экрана,
            // иначе анимация начинается уже на виду и выглядит запоздалой
            { rootMargin: '0px 0px -12% 0px', threshold: 0.05 },
        );

        targets.forEach((el) => {
            // Блок, уже видимый при загрузке, показываем без анимации:
            // первый экран не должен появляться с задержкой
            const rect = el.getBoundingClientRect();
            if (rect.top < window.innerHeight * 0.9) {
                el.classList.add('is-visible');
                return;
            }
            // Шторка закрывает заголовок через clip-path, а Chrome считает
            // обрезанный так элемент невидимым — наблюдатель не сработал бы
            // никогда. За шторкой следим по её родителю
            const watch = el.dataset.reveal === 'wipe' && el.parentElement ? el.parentElement : el;
            watched.set(watch, [...(watched.get(watch) ?? []), el]);
            io.observe(watch);
        });

        return () => io.disconnect();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, deps);
}
