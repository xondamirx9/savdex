import { Loader2 } from 'lucide-react';
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { cn } from '@/lib/cn';

export type ButtonVariant = 'primary' | 'secondary' | 'outline' | 'ghost' | 'danger';
export type ButtonSize = 'sm' | 'md' | 'lg';

const VARIANTS: Record<ButtonVariant, string> = {
    primary: 'bg-primary-700 text-white border-transparent hover:bg-primary-600 hover:shadow-lift',
    secondary: 'bg-surface text-ink border-line-strong hover:border-muted hover:bg-canvas',
    outline: 'bg-surface text-primary-700 border-primary-700 hover:bg-primary-50',
    ghost: 'bg-transparent text-muted border-transparent hover:bg-canvas hover:text-ink',
    danger: 'bg-danger text-white border-transparent hover:bg-red-700',
};

/**
 * Высота по шкале 32 / 40 / 48 (docs/DESIGN.md §5.1).
 * Другие значения не вводить — разнобой в пару пикселей и делает
 * интерфейс визуально неаккуратным.
 */
const SIZES: Record<ButtonSize, string> = {
    sm: 'h-8 px-3 text-[13px] gap-1.5',
    md: 'h-10 px-[18px] text-[15px] gap-2',
    lg: 'h-12 px-7 text-base gap-2',
};

interface Props extends Omit<ButtonHTMLAttributes<HTMLButtonElement>, 'className'> {
    variant?: ButtonVariant;
    size?: ButtonSize;
    block?: boolean;
    loading?: boolean;
    /** Оставляет только иконку. Обязательно задайте aria-label. */
    iconOnly?: boolean;
    children?: ReactNode;
    className?: string;
}

export function Button({
    variant = 'primary',
    size = 'md',
    block = false,
    loading = false,
    iconOnly = false,
    disabled,
    children,
    className,
    type = 'button',
    ...rest
}: Props) {
    return (
        <button
            type={type}
            /**
             * Кнопка блокируется на время запроса — правило 10 из §1 QA.md.
             * Ширина при этом не меняется: спиннер занимает место иконки,
             * текст остаётся на месте, вёрстка не прыгает (NEG-14).
             */
            disabled={disabled || loading}
            aria-busy={loading || undefined}
            className={cn(
                'relative inline-flex items-center justify-center rounded-btn border font-semibold leading-none whitespace-nowrap',
                'transition-[background-color,border-color,box-shadow,color] duration-150 ease-out',
                'disabled:pointer-events-none disabled:opacity-50',
                // Область нажатия не меньше 44×44 даже у мелких кнопок (A11Y-06)
                "after:absolute after:top-1/2 after:left-1/2 after:h-11 after:min-w-11 after:-translate-x-1/2 after:-translate-y-1/2 after:content-['']",
                VARIANTS[variant],
                iconOnly ? 'w-10 px-0' : SIZES[size],
                block && 'w-full',
                className,
            )}
            {...rest}
        >
            {loading && <Loader2 aria-hidden className="size-4 animate-spin" />}
            {children}
        </button>
    );
}
