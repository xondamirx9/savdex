import { router } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { Info, Lock } from 'lucide-react';
import { BarRow, Metric, Panel, formatNumber, type MetricData } from '@/components/cabinet';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { routes } from '@/routes';

interface Benchmark {
    label: string;
    you: number;
    median: number;
    position: number;
    verdict: string;
    tone: string;
}

interface Props {
    metrics: Record<'impressions' | 'views' | 'unlocks' | 'conversion', MetricData> | null;
    series: Record<'impressions' | 'views' | 'unlocks', number[]> | null;
    funnel: { label: string; value: number; share: number; tone: string }[];
    geography: { label: string; value: number }[];
    queries: { query: string; impressions: number; clicks: number; ctr: number }[];
    benchmark: Benchmark[];
    periods: Record<string, string>;
    period: number;
    advanced: boolean;
    plan: { name: string } | null;
}

const TONE_COLOR: Record<string, string> = {
    primary: 'var(--primary-700)',
    success: 'var(--success)',
    warning: 'var(--warning)',
};

export default function Analytics({
    metrics,
    series,
    funnel,
    geography,
    queries,
    benchmark,
    periods,
    period,
    advanced,
    plan,
}: Props) {
    if (!metrics || !series) {
        return (
            <CabinetLayout title="Аналитика" heading="Аналитика">
                <div className="card empty">
                    <p className="t-h4">Данных пока нет</p>
                    <p className="t-sm muted mt-8">Аналитика появится, когда объявления начнут показываться в выдаче.</p>
                </div>
            </CabinetLayout>
        );
    }

    const suffix = `к прошлым ${period} дн.`;
    const weak = benchmark.find((b) => b.tone === 'warning');

    return (
        <CabinetLayout
            title="Аналитика"
            heading="Аналитика"
            subheading={advanced ? `Расширенная — входит в тариф ${plan?.name}` : `Базовая — тариф ${plan?.name}`}
            actions={
                <select
                    className="select"
                    style={{ width: 'auto' }}
                    aria-label="Период"
                    value={period}
                    onChange={(e) =>
                        router.get(routes.cabinetAnalytics, { period: e.target.value }, { preserveState: true })
                    }
                >
                    {Object.entries(periods).map(([days, label]) => (
                        <option key={days} value={days}>
                            {label}
                        </option>
                    ))}
                </select>
            }
        >
            <div className="grid grid-4 grid-tight">
                <Metric label="Показы в выдаче" data={metrics.impressions} series={series.impressions} deltaSuffix={suffix} />
                <Metric label="Просмотры карточек" data={metrics.views} series={series.views} deltaSuffix={suffix} />
                <Metric label="Открыли контакт" data={metrics.unlocks} series={series.unlocks} deltaSuffix={suffix} />
                <Metric label="Конверсия в контакт" data={metrics.conversion} deltaSuffix={suffix} />
            </div>

            {/* Сравнение с категорией — главный мотиватор: собственные
                цифры без ориентира не говорят, хорошо это или плохо */}
            {advanced && benchmark.length > 0 && (
                <Panel title="Сравнение с категорией" className="mt-24">
                    <div className="stack-16">
                        {benchmark.map((b) => (
                            <div key={b.label} className="benchmark">
                                <span>{b.label}</span>
                                <div className="benchmark-scale">
                                    <span className="benchmark-median" style={{ left: '50%' }} title="Медиана категории" />
                                    <span
                                        className="benchmark-you"
                                        style={{
                                            left: `${b.position}%`,
                                            background: b.tone === 'warning' ? 'var(--warning)' : undefined,
                                        }}
                                        title={`Ваш показатель: ${b.you}`}
                                    />
                                </div>
                                <b
                                    className="nowrap"
                                    style={{ color: b.tone === 'warning' ? 'var(--warning)' : undefined }}
                                >
                                    {b.verdict}
                                </b>
                            </div>
                        ))}
                    </div>

                    {weak && (
                        <div className="alert alert-warning mt-16">
                            <Info aria-hidden className="size-5" />
                            <div>
                                Вас находят, но реже открывают контакт. Обычно причина — отсутствие цены или мало
                                фотографий. <Link href={routes.cabinetListings}>Проверить объявления</Link>
                            </div>
                        </div>
                    )}
                </Panel>
            )}

            <Panel title={`Воронка за ${period} дн.`} className="mt-24">
                {funnel.map((step) => (
                    <div key={step.label} className="funnel-step">
                        <span>{step.label}</span>
                        <div
                            className="funnel-bar"
                            style={{
                                // Минимум 6 % — иначе последние шаги воронки
                                // схлопываются в невидимую полоску
                                width: `${Math.max(6, step.share)}%`,
                                background: TONE_COLOR[step.tone],
                            }}
                        >
                            {formatNumber(step.value)}
                        </div>
                        <span className="t-sm muted">{step.share} %</span>
                    </div>
                ))}
            </Panel>

            <div className="grid grid-2 mt-24">
                <Panel title="География спроса">
                    {geography.length === 0 ? (
                        <p className="muted t-sm">Пока никто не открывал ваши контакты — географию считать не из чего.</p>
                    ) : (
                        geography.map((g) => (
                            <BarRow key={g.label} label={g.label} value={g.value} max={geography[0].value} />
                        ))
                    )}
                </Panel>

                <Panel title="По каким запросам вас находили">
                    {!advanced ? (
                        <div className="empty" style={{ padding: '24px 8px' }}>
                            <div className="empty-icon">
                                <Lock aria-hidden className="size-6" />
                            </div>
                            <p className="t-sm muted" style={{ maxWidth: 320, margin: '0 auto' }}>
                                Поисковые запросы входят в тарифы Business и Premium.
                            </p>
                            <Link href={routes.pricing} className="btn btn-outline btn-sm mt-16">
                                Сравнить тарифы
                            </Link>
                        </div>
                    ) : queries.length === 0 ? (
                        <p className="muted t-sm">Данных за период нет.</p>
                    ) : (
                        <div className="table-wrap table-cards" style={{ border: 'none' }}>
                            <table className="table" style={{ minWidth: 0 }}>
                                <thead>
                                    <tr>
                                        <th>Запрос</th>
                                        <th className="num">Показы</th>
                                        <th className="num">Переходы</th>
                                        <th className="num">CTR</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    {queries.map((q) => (
                                        <tr key={q.query}>
                                            <td data-label="Запрос">{q.query}</td>
                                            <td data-label="Показы" className="num">
                                                {formatNumber(q.impressions)}
                                            </td>
                                            <td data-label="Переходы" className="num">
                                                {formatNumber(q.clicks)}
                                            </td>
                                            <td data-label="CTR" className="num">
                                                {q.ctr} %
                                            </td>
                                        </tr>
                                    ))}
                                </tbody>
                            </table>
                        </div>
                    )}
                </Panel>
            </div>
        </CabinetLayout>
    );
}
