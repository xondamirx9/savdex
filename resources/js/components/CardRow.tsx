import { ChevronLeft, ChevronRight } from 'lucide-react';
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';

import { t } from '@/lib/i18n';

/**
 * Лента карточек в один ряд со стрелками по бокам.
 *
 * Прокрутка остаётся нативной: колесо, свайп и клавиши работают как
 * прежде, кнопки лишь листают ряд на видимую ширину. Стрелка у своего
 * края не показывается — неактивная кнопка ничего не сообщает,
 * а поверх крайней карточки висит и закрывает её.
 *
 * Разметка ряда осталась прежней (.card-row), поэтому компонент
 * подходит любой ленте главной без правки стилей карточек.
 */
export function CardRow({ children }: { children: ReactNode }) {
    const rowRef = useRef<HTMLDivElement>(null);
    const [edges, setEdges] = useState({ start: true, end: true });

    const sync = useCallback(() => {
        const el = rowRef.current;

        if (!el) return;

        // Запас в 2 пикселя — на дробную ширину при масштабировании
        // страницы: без него стрелка «вперёд» оставалась в самом конце
        const max = el.scrollWidth - el.clientWidth;

        setEdges({ start: el.scrollLeft <= 2, end: el.scrollLeft >= max - 2 });
    }, []);

    useEffect(() => {
        const el = rowRef.current;

        if (!el) return;

        sync();

        // Ширина ряда меняется при повороте телефона и смене раскладки
        // сетки — тогда лента может перестать прокручиваться вовсе
        const observer = new ResizeObserver(sync);
        observer.observe(el);

        return () => observer.disconnect();
    }, [sync, children]);

    const page = (direction: 1 | -1) => {
        const el = rowRef.current;

        if (!el) return;

        // Шаг — видимая ширина минус одна карточка: соседняя остаётся
        // на экране и связывает «страницы» ленты между собой
        const card = el.querySelector<HTMLElement>(':scope > *');
        const step = Math.max(el.clientWidth - (card?.offsetWidth ?? 0), el.clientWidth * 0.6);

        el.scrollBy({ left: direction * step, behavior: 'smooth' });
    };

    return (
        <div className="card-rail">
            <div className="card-row" ref={rowRef} onScroll={sync} data-reveal-stagger>
                {children}
            </div>

            {!edges.start && (
                <button
                    type="button"
                    className="card-rail-nav card-rail-nav--prev"
                    aria-label={t('home.row_prev')}
                    onClick={() => page(-1)}
                >
                    <ChevronLeft aria-hidden className="size-5" />
                </button>
            )}

            {!edges.end && (
                <button
                    type="button"
                    className="card-rail-nav card-rail-nav--next"
                    aria-label={t('home.row_next')}
                    onClick={() => page(1)}
                >
                    <ChevronRight aria-hidden className="size-5" />
                </button>
            )}
        </div>
    );
}
