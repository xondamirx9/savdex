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
 * Пункт списка.
 *
 * Выбор и раскрытие разведены. Раньше подрубрики показывались только
 * у выбранной ветки: посмотреть, что внутри «IT-услуг», не выбрав их,
 * было нельзя, а выбрав — лента уже перезагружалась. Теперь у ветки
 * с подпунктами своя стрелка: она раскрывает список и ничего не
 * фильтрует. Подпись ветки тоже раскрывает и сворачивает её, но
 * вдобавок выбирает: стрелку-мишень в 28 пикселей ищут не все, а по
 * названию нажимают все.
 *
 * Ветка выбранного пункта раскрыта сразу: страница, открытая по
 * ссылке с фильтром, должна показывать, где этот фильтр стоит.
 */
function Option({
    option,
    name,
    value,
    onPick,
    expanded,
    onToggle,
    nested = false,
}: {
    option: FilterOption;
    name: string;
    value: string;
    onPick: (id: string) => void;
    expanded: Record<string, boolean>;
    onToggle: (id: string, next: boolean) => void;
    nested?: boolean;
}) {
    const children = option.children ?? [];
    const active = value === option.id;
    const childActive = children.some((child) => child.id === value);
    const open = expanded[option.id] ?? (active || childActive);

    return (
        <>
            <div className={cn('board-filter-row', (active || childActive) && 'is-active', nested && 'board-filter-row--child')}>
                <label className="check board-filter">
                    <input
                        type="radio"
                        name={name}
                        checked={active}
                        onChange={() => onPick(option.id)}
                        // Подпись ветки раскрывает и сворачивает её так же,
                        // как стрелка. На onClick, а не на onChange: у уже
                        // выбранного переключателя change не приходит,
                        // и нажатие на подпись выбранной ветки ничего не
                        // делало. Клик по <label> браузер передаёт сюда же,
                        // поэтому срабатывает ровно один раз
                        onClick={() => {
                            if (children.length > 0) onToggle(option.id, !open);
                        }}
                    />
                    <span className="board-filter-label">{option.label}</span>
                    {option.count !== undefined && <span className="check-count">{option.count}</span>}
                </label>

                {children.length > 0 && (
                    <button
                        type="button"
                        className="board-filter-toggle"
                        aria-expanded={open}
                        aria-label={option.label}
                        onClick={() => onToggle(option.id, !open)}
                    >
                        <ChevronDown aria-hidden className="size-4" />
                    </button>
                )}
            </div>

            {open && children.length > 0 && (
                <div className="board-filter-kids">
                    {children.map((child) => (
                        <Option
                            key={child.id}
                            option={child}
                            name={name}
                            value={value}
                            onPick={onPick}
                            expanded={expanded}
                            onToggle={onToggle}
                            nested
                        />
                    ))}
                </div>
            )}
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
    /*
     * Какие ветки раскрыты. Пункта тут нет, пока его не трогали: до
     * первого нажатия раскрытой считается ветка выбранного пункта,
     * дальше решает человек.
     */
    const [expanded, setExpanded] = useState<Record<string, boolean>>({});

    const toggle = (id: string, next: boolean) => setExpanded((prev) => ({ ...prev, [id]: next }));

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
                                expanded={expanded}
                                onToggle={toggle}
                            />
                        ))}
                    </div>
                </div>

                {children}
            </div>
        </aside>
    );
}
