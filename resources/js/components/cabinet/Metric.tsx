import { ArrowDown, ArrowUp, Minus } from 'lucide-react';
import { cn } from '@/lib/cn';

export interface MetricData {
    value: number;
    delta: number | null;
    format: 'int' | 'percent';
}

/** Разделитель разрядов — узкий пробел: 4 218 читается быстрее, чем 4218. */
export function formatNumber(value: number): string {
    return value.toLocaleString('ru-RU').replace(/ /g, ' ');
}

/**
 * Спарклайн: направление, а не точные значения.
 *
 * Оси и подписи намеренно отсутствуют — на высоте 34 px они нечитаемы,
 * а точные цифры смотрят в разделе аналитики.
 */
function Sparkline({ points, tone }: { points: number[]; tone: string }) {
    if (points.length < 2) return null;

    const max = Math.max(...points, 1);
    const min = Math.min(...points);
    const span = max - min || 1;

    const path = points
        .map((p, i) => {
            const x = (i / (points.length - 1)) * 100;
            const y = 30 - ((p - min) / span) * 26;
            return `${x.toFixed(1)},${y.toFixed(1)}`;
        })
        .join(' ');

    return (
        <svg className="sparkline" viewBox="0 0 100 34" preserveAspectRatio="none" aria-hidden="true">
            <polyline points={path} fill="none" stroke={tone} strokeWidth="2" vectorEffect="non-scaling-stroke" />
        </svg>
    );
}

export function Metric({
    label,
    data,
    series,
    deltaSuffix = 'к прошлым 30 дн.',
}: {
    label: string;
    data: MetricData;
    series?: number[];
    deltaSuffix?: string;
}) {
    const up = (data.delta ?? 0) > 0;
    const down = (data.delta ?? 0) < 0;
    const Icon = up ? ArrowUp : down ? ArrowDown : Minus;

    const value = data.format === 'percent' ? `${data.value.toFixed(1)} %` : formatNumber(data.value);

    // Конверсия измеряется в процентах, поэтому её изменение —
    // в процентных пунктах: «+2 %» и «+2 п.п.» это разные величины
    const deltaUnit = data.format === 'percent' ? ' п.п.' : ' %';

    return (
        <div className="metric">
            <div className="metric-label">{label}</div>
            <div className="metric-value">{value}</div>

            {data.delta === null ? (
                <div className="metric-delta delta-flat">нет данных за прошлый период</div>
            ) : (
                <div className={cn('metric-delta', up ? 'delta-up' : down ? 'delta-down' : 'delta-flat')}>
                    <Icon aria-hidden className="size-3.5" />
                    {data.delta > 0 ? '+' : ''}
                    {data.delta}
                    {deltaUnit} {deltaSuffix}
                </div>
            )}

            {series && (
                <Sparkline
                    points={series}
                    tone={up ? 'var(--success)' : down ? 'var(--danger)' : 'var(--primary-500)'}
                />
            )}
        </div>
    );
}
