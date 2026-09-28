import { useEffect, useLayoutEffect, useRef, useState } from 'react';

import { formatNumber } from '@/components/cabinet';

/**
 * На сервере слоя нет — там достаточно обычного эффекта. Без этой
 * подмены React ругается на useLayoutEffect при серверной отрисовке.
 */
const useBeforePaint = typeof window === 'undefined' ? useEffect : useLayoutEffect;

/**
 * Счётчик, добегающий до значения.
 *
 * Числа на полосе показателей — первое, что видит посетитель: «1 193
 * компании» работает доводом, только если взгляд на нём задержался.
 * Неподвижное число сливается с остальной вёрсткой, растущее — нет.
 *
 * Обнуление делается до отрисовки, а не в обычном эффекте: разметка
 * приходит с сервера с итоговым числом, и обычный эффект успел бы
 * показать его на кадр раньше сброса — число моргнуло бы.
 *
 * Разгон идёт по кубической кривой с замедлением к концу: равномерный
 * счёт читается как индикатор загрузки, а не как рост.
 */
export function CountUp({ value, duration = 1100 }: { value: number; duration?: number }) {
    const [shown, setShown] = useState(value);
    const [armed, setArmed] = useState(false);
    const ref = useRef<HTMLSpanElement>(null);

    useBeforePaint(() => {
        // Нечего разгонять, и системную настройку уважаем: там число
        // просто стоит на месте
        if (value <= 0 || window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;

        setShown(0);
        setArmed(true);
    }, [value]);

    useEffect(() => {
        if (!armed) return;

        const el = ref.current;

        if (el === null) return;

        let frame = 0;

        const run = () => {
            const started = performance.now();

            const tick = (now: number) => {
                const passed = Math.min(1, (now - started) / duration);
                const eased = 1 - (1 - passed) ** 3;

                setShown(Math.round(value * eased));

                if (passed < 1) frame = requestAnimationFrame(tick);
            };

            frame = requestAnimationFrame(tick);
        };

        // Полоса показателей стоит на первом экране и видна сразу.
        // Наблюдатель нужен для тех же чисел ниже по странице: счёт,
        // отработавший до прокрутки, посетитель бы не увидел
        if (el.getBoundingClientRect().top < window.innerHeight) {
            run();

            return () => cancelAnimationFrame(frame);
        }

        const io = new IntersectionObserver(
            (entries) => {
                if (!entries[0].isIntersecting) return;

                io.disconnect();
                run();
            },
            { threshold: 0.2 },
        );

        io.observe(el);

        return () => {
            io.disconnect();
            cancelAnimationFrame(frame);
        };
    }, [armed, value, duration]);

    return <span ref={ref}>{formatNumber(shown)}</span>;
}
