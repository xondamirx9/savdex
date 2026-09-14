import { ChevronDown, Menu } from 'lucide-react';
import { useState } from 'react';

import { cn } from '@/lib/cn';

/**
 * Панель фильтра слева — одна на страницы-ленты: тендеры и IT-услуги.
 *
 * Список открыт целиком и никуда не прокручивается: своей высоты у
 * панели нет, поэтому второй полосы прокрутки на странице не
 * появляется. На узком экране список сворачивается под кнопку — там
 * развёрнутый перечень занял бы первый экран до самих карточек.
 */
export interface FilterOption {
    /** Пустая строка — «все»: такой пункт сбрасывает фильтр. */
    id: string;
    label: string;
    children?: FilterOption[];
}

function Option({
    option,
    value,
    onPick,
    nested = false,
}: {
    option: FilterOption;
    value: string;
    onPick: (id: string) => void;
    nested?: boolean;
}) {
    const active = value === option.id;
    const childActive = (option.children ?? []).some((child) => child.id === value);

    return (
        <>
            <button
                type="button"
                className={cn('board-filter', nested && 'board-filter--child', (active || childActive) && 'is-active')}
                aria-pressed={active}
                onClick={() => onPick(option.id)}
            >
                {option.label}
            </button>

            {/* Подрубрики раскрываются только у выбранной ветки: полный
                список второго уровня превращает панель в простыню */}
            {(active || childActive) &&
                (option.children ?? []).map((child) => (
                    <Option key={child.id} option={child} value={value} onPick={onPick} nested />
                ))}
        </>
    );
}

export function BoardFilter({
    title,
    options,
    value,
    onPick,
}: {
    title: string;
    options: FilterOption[];
    value: string;
    onPick: (id: string) => void;
}) {
    const [open, setOpen] = useState(false);

    return (
        <aside className="board-panel">
            <button
                type="button"
                className="board-panel-toggle"
                aria-expanded={open}
                onClick={() => setOpen((v) => !v)}
            >
                <Menu aria-hidden className="size-4" />
                <span>{title}</span>
                <ChevronDown aria-hidden className="size-4" />
            </button>

            <span className="board-panel-title">{title}</span>

            <div className={cn('board-filter-list', open && 'is-open')}>
                {options.map((option) => (
                    <Option key={option.id || 'all'} option={option} value={value} onPick={onPick} />
                ))}
            </div>
        </aside>
    );
}
