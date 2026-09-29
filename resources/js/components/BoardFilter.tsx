import { ChevronDown, Menu } from 'lucide-react';
import type { ReactNode } from 'react';
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
    /** Сколько найдётся при выборе. undefined — числа нет, ничего не рисуем */
    count?: number;
    children?: FilterOption[];
}

/**
 * Пункт — переключатель, как в фильтрах каталога и компаний.
 *
 * Кружок сразу показывает, что выбор один из списка и что выбрано
 * сейчас: прежний список ссылок отличал выбранный пункт только цветом,
 * и на длинном перечне его приходилось искать глазами.
 */
function Option({
    option,
    name,
    value,
    onPick,
    nested = false,
}: {
    option: FilterOption;
    name: string;
    value: string;
    onPick: (id: string) => void;
    nested?: boolean;
}) {
    const active = value === option.id;
    const childActive = (option.children ?? []).some((child) => child.id === value);

    return (
        <>
            <label className={cn('check board-filter', nested && 'board-filter--child')}>
                <input
                    type="radio"
                    name={name}
                    checked={active}
                    onChange={() => onPick(option.id)}
                />
                <span className={cn('board-filter-label', (active || childActive) && 'is-active')}>
                    {option.label}
                </span>
                {option.count !== undefined && <span className="check-count">{option.count}</span>}
            </label>

            {/* Подрубрики раскрываются только у выбранной ветки: полный
                список второго уровня превращает панель в простыню */}
            {(active || childActive) &&
                (option.children ?? []).map((child) => (
                    <Option key={child.id} option={child} name={name} value={value} onPick={onPick} nested />
                ))}
        </>
    );
}

export function BoardFilter({
    title,
    name,
    options,
    value,
    onPick,
    children,
}: {
    title: string;
    /** Имя группы переключателей: у двух панелей на странице оно своё */
    name: string;
    options: FilterOption[];
    value: string;
    onPick: (id: string) => void;
    /**
     * Дополнительные фильтры под списком — город, галочки. Тендерам
     * они не нужны, поэтому не часть компонента: он отвечает за
     * перечень разделов, а что ставить под ним, решает страница.
     */
    children?: ReactNode;
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

            {/* Внутри списка, а не рядом: на узком экране панель
                сворачивается под кнопку целиком, вместе с городом
                и галочками — иначе свёрнутый фильтр оставлял бы
                половину себя на экране */}
            <div className={cn('board-filter-list', open && 'is-open')}>
                <div className="board-group">
                    <span className="board-panel-title">{title}</span>

                    <div className="board-filter-items">
                        {options.map((option) => (
                            <Option
                                key={option.id || 'all'}
                                option={option}
                                name={name}
                                value={value}
                                onPick={onPick}
                            />
                        ))}
                    </div>
                </div>

                {children}
            </div>
        </aside>
    );
}
