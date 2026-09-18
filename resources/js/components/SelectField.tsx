import { Check, ChevronDown } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { cn } from '@/lib/cn';
import { useDismiss } from '@/lib/useDismiss';

/**
 * Выпадающий список площадки.
 *
 * Системный список <select> не поддаётся оформлению: браузер рисует его
 * сам — прямые углы, своя синяя подсветка, свой шрифт. Рядом с панелью
 * поиска это выглядит чужим окном, поэтому на мыши список рисуется
 * разметкой и подчиняется стилям сайта.
 *
 * На сенсорном экране остаётся системный <select>: телефон открывает
 * привычное колесо выбора внизу экрана, оно удобнее любого нашего
 * списка и не требует точного попадания пальцем.
 */
export interface SelectOption {
    value: string;
    label: string;
}

export function SelectField({
    value,
    onChange,
    options,
    placeholder,
    ariaLabel,
    className,
    id,
}: {
    value: string;
    onChange: (value: string) => void;
    options: SelectOption[];
    /**
     * Пункт «любой»: пустое значение, всегда первым в списке. Без него
     * список считается обязательным — как сортировка, где пустого
     * значения не бывает.
     */
    placeholder?: string;
    ariaLabel: string;
    className?: string;
    /**
     * Для <label for>. Кнопка — размечаемый элемент, как и <select>,
     * поэтому подпись остаётся кликабельной в обоих режимах.
     */
    id?: string;
}) {
    const [custom, setCustom] = useState(false);
    const [open, setOpen] = useState(false);
    const [cursor, setCursor] = useState(0);
    const ref = useDismiss(() => setOpen(false));
    const listRef = useRef<HTMLDivElement>(null);

    const all: SelectOption[] =
        placeholder === undefined ? options : [{ value: '', label: placeholder }, ...options];
    const current = all.find((o) => o.value === value) ?? all[0];

    /*
     * Проверка указателя живёт в эффекте, а не в первом рендере:
     * на сервере window нет, и разметка обязана совпасть с серверной.
     */
    useEffect(() => {
        setCustom(window.matchMedia('(pointer: fine)').matches);
    }, []);

    // Открытый список ведёт курсор от выбранного пункта
    useEffect(() => {
        if (open) setCursor(Math.max(0, all.findIndex((o) => o.value === value)));
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [open]);

    // Подсвеченный пункт всегда в поле зрения при ходьбе стрелками
    useEffect(() => {
        if (!open) return;

        listRef.current?.querySelector('[data-cursor="true"]')?.scrollIntoView({ block: 'nearest' });
    }, [cursor, open]);

    if (!custom) {
        return (
            <select
                id={id}
                className={cn('select', className)}
                aria-label={ariaLabel}
                value={value}
                onChange={(e) => onChange(e.target.value)}
            >
                {all.map((o) => (
                    <option key={o.value} value={o.value}>
                        {o.label}
                    </option>
                ))}
            </select>
        );
    }

    const pick = (option: SelectOption) => {
        onChange(option.value);
        setOpen(false);
    };

    const onKey = (e: React.KeyboardEvent) => {
        if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
            e.preventDefault();

            if (!open) {
                setOpen(true);

                return;
            }

            setCursor((i) => {
                const next = e.key === 'ArrowDown' ? i + 1 : i - 1;

                return Math.min(all.length - 1, Math.max(0, next));
            });

            return;
        }

        if (e.key === 'Home' || e.key === 'End') {
            if (!open) return;
            e.preventDefault();
            setCursor(e.key === 'Home' ? 0 : all.length - 1);

            return;
        }

        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            open ? pick(all[cursor]) : setOpen(true);

            return;
        }

        if (e.key === 'Escape' && open) {
            e.preventDefault();
            setOpen(false);
        }
    };

    return (
        <div className={cn('dropdown select-field', className)} ref={ref}>
            <button
                id={id}
                type="button"
                className={cn('select select-field-btn', value === '' && 'is-empty')}
                aria-haspopup="listbox"
                aria-expanded={open}
                aria-label={ariaLabel}
                onKeyDown={onKey}
                onClick={(e) => {
                    e.stopPropagation();
                    setOpen((v) => !v);
                }}
            >
                <span className="select-field-value">{current.label}</span>
                <ChevronDown aria-hidden className="size-4 select-field-arrow" />
            </button>

            <div
                className={cn('dropdown-menu select-menu', open && 'open')}
                role="listbox"
                aria-label={ariaLabel}
                ref={listRef}
            >
                {all.map((option, i) => (
                    <button
                        key={option.value || 'any'}
                        type="button"
                        role="option"
                        aria-selected={option.value === value}
                        data-cursor={i === cursor}
                        className={cn('dropdown-item select-option', i === cursor && 'is-cursor')}
                        onMouseEnter={() => setCursor(i)}
                        onClick={() => pick(option)}
                    >
                        {option.label}
                        {option.value === value && <Check aria-hidden className="size-4 select-option-mark" />}
                    </button>
                ))}
            </div>
        </div>
    );
}
