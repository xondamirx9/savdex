import { Link } from '@/components/ui/Link';
import { Star } from 'lucide-react';
import type { ComponentType, ReactNode } from 'react';
import { cn } from '@/lib/cn';

export { Metric, formatNumber } from './Metric';
export type { MetricData } from './Metric';

/** Карточка-раздел с заголовком и необязательным действием справа. */
export function Panel({
    title,
    action,
    className,
    children,
}: {
    title?: string;
    action?: ReactNode;
    className?: string;
    children: ReactNode;
}) {
    return (
        <section className={cn('card', className)}>
            {(title || action) && (
                <div className="row-between" style={{ marginBottom: 18, gap: 12 }}>
                    {title && <h2 className="t-h3">{title}</h2>}
                    {action}
                </div>
            )}
            {children}
        </section>
    );
}

/** Полоска прогресса с подписью и числом. */
export function LimitBar({
    label,
    used,
    total,
    tone = 'primary',
}: {
    label: string;
    used: number;
    total: number | null;
    tone?: 'primary' | 'warning';
}) {
    // null — безлимит: рисовать шкалу не от чего, и «12 / ∞» бессмысленно
    const share = total === null || total === 0 ? 0 : Math.min(100, (used / total) * 100);
    const tight = total !== null && share >= 80;

    return (
        <div>
            <div className="row-between t-sm" style={{ marginBottom: 6 }}>
                <span>{label}</span>
                <b>{total === null ? `${used} · без ограничений` : `${used} / ${total}`}</b>
            </div>
            {total !== null && (
                <div className="progress">
                    <div
                        className="progress-fill"
                        style={{
                            width: `${share}%`,
                            background: tight || tone === 'warning' ? 'var(--warning)' : undefined,
                        }}
                    />
                </div>
            )}
        </div>
    );
}

/** Горизонтальная полоса в списках «география», «источники». */
export function BarRow({ label, value, max, suffix }: { label: string; value: number; max: number; suffix?: string }) {
    return (
        <div className="bar-row">
            <span className="t-sm">{label}</span>
            <div className="bar-track">
                <div className="bar-fill" style={{ width: `${max > 0 ? (value / max) * 100 : 0}%` }} />
            </div>
            <span className="bar-val">
                {value}
                {suffix}
            </span>
        </div>
    );
}

/** Оценка звёздами. Число дублируется текстом — цвет не единственный носитель. */
export function Stars({ value, size = 16 }: { value: number; size?: number }) {
    return (
        <span className="stars" role="img" aria-label={`Оценка ${value} из 5`}>
            {[1, 2, 3, 4, 5].map((i) => (
                <Star
                    key={i}
                    aria-hidden
                    className={cn(i > Math.round(value) && 'star-off')}
                    style={{ width: size, height: size }}
                    fill={i <= Math.round(value) ? 'currentColor' : 'none'}
                />
            ))}
        </span>
    );
}

/**
 * Пустое состояние.
 *
 * Пустая страница читается как поломка, поэтому объясняем, что здесь
 * будет и что для этого сделать — с кнопкой, а не просто текстом.
 */
export function Empty({
    icon: Icon,
    title,
    text,
    action,
}: {
    icon: ComponentType<{ className?: string; 'aria-hidden'?: boolean }>;
    title: string;
    text?: string;
    action?: { href: string; label: string };
}) {
    return (
        <div className="card empty">
            <div className="empty-icon">
                <Icon aria-hidden className="size-7" />
            </div>
            <p className="t-h4">{title}</p>
            {text && (
                <p className="t-sm muted mt-8" style={{ maxWidth: 420, margin: '8px auto 0' }}>
                    {text}
                </p>
            )}
            {action && (
                <Link href={action.href} className="btn btn-primary mt-24">
                    {action.label}
                </Link>
            )}
        </div>
    );
}

/** Вкладки со счётчиками. Управляемые: состояние держит страница. */
export function Tabs({
    items,
    active,
    onChange,
    label,
}: {
    items: { key: string; label: string; count?: number }[];
    active: string;
    onChange: (key: string) => void;
    label: string;
}) {
    return (
        <div role="tablist" className="tabs" aria-label={label} style={{ marginBottom: 20 }}>
            {items.map((t) => (
                <button
                    key={t.key}
                    role="tab"
                    className="tab"
                    aria-selected={t.key === active}
                    tabIndex={t.key === active ? 0 : -1}
                    onClick={() => onChange(t.key)}
                >
                    {t.label}
                    {t.count !== undefined && ` · ${t.count}`}
                </button>
            ))}
        </div>
    );
}
