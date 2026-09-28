import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { formatNumber } from '@/components/cabinet';

/** На сервере useLayoutEffect не выполняется — там берём обычный. */
const useIsoLayoutEffect = typeof window !== 'undefined' ? useLayoutEffect : useEffect;

/** Замедление к концу: число разгоняется и мягко встаёт на место. */
const easeOutCubic = (x: number): number => 1 - Math.pow(1 - x, 3);

/**
 * Число, которое «набегает» от нуля до значения, когда попадает на экран.
 *
 * Сервер отдаёт в разметке настоящее число: поисковик и человек без
 * JavaScript видят верную цифру. Анимация — только поверх неё, в браузере,
 * и только один раз: при обратной прокрутке счёт не повторяется.
 *
 * Скринридер получает итоговое число сразу (sr-only), а бегущие цифры
 * от него скрыты — иначе он зачитывал бы промежуточные значения.
 * При «уменьшить движение» в системе число показывается сразу.
 */
export function CountUp({ value, duration = 1400 }: { value: number; duration?: number }) {
    const ref = useRef<HTMLSpanElement>(null);
    const [shown, setShown] = useState(value);

    useIsoLayoutEffect(() => {
        const el = ref.current;

        if (el === null || value <= 0 || window.matchMedia('(prefers-reduced-motion: reduce)').matches) {
            setShown(value);

            return;
        }

        // До первой отрисовки — ноль, чтобы не мелькнуло итоговое число
        setShown(0);

        let frame = 0;
        let start = 0;

        const tick = (now: number) => {
            if (start === 0) start = now;
            const progress = Math.min(1, (now - start) / duration);
            setShown(Math.round(easeOutCubic(progress) * value));

            if (progress < 1) frame = requestAnimationFrame(tick);
        };

        const io = new IntersectionObserver(
            (entries) => {
                if (entries.some((e) => e.isIntersecting)) {
                    io.disconnect();
                    frame = requestAnimationFrame(tick);
                }
            },
            { threshold: 0.3 },
        );

        io.observe(el);

        return () => {
            io.disconnect();
            cancelAnimationFrame(frame);
        };
    }, [value, duration]);

    return (
        <>
            <span ref={ref} aria-hidden="true">
                {formatNumber(shown)}
            </span>
            <span className="sr-only">{formatNumber(value)}</span>
        </>
    );
}
