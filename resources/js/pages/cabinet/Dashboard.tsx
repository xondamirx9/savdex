import { usePage } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import {
    Building2,
    Clock,
    CreditCard,
    Eye,
    FileText,
    Plus,
    Rocket,
    Star,
    TriangleAlert,
} from 'lucide-react';
import type { ComponentType } from 'react';
import { LimitBar, Metric, Panel, type MetricData } from '@/components/cabinet';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { cn } from '@/lib/cn';
import { pluralize } from '@/lib/plural';
import { routes } from '@/routes';
import type { SharedProps } from '@/types';

interface Props {
    company: { name: string; slug: string; completeness: number; missing: string[] } | null;
    metrics: Record<'impressions' | 'views' | 'unlocks' | 'conversion', MetricData> | null;
    series: Record<'impressions' | 'views' | 'unlocks', number[]> | null;
    events: { id: number; type: string; tone: string; message: string; url: string | null; ago: string }[];
    limits: {
        listings: { used: number; total: number | null };
        contacts: { used: number; total: number | null };
        promo: { used: number; total: number };
        resets_at: string | null;
    } | null;
    plan: { name: string; until: string | null } | null;
    expiring: number;
    drafts: number;
}

const EVENT_ICONS: Record<string, ComponentType<{ className?: string; 'aria-hidden'?: boolean }>> = {
    unlock: Eye,
    review: Star,
    promotion: Rocket,
    expiry: Clock,
    moderation: FileText,
    payment: CreditCard,
};

const TONE_CLASS: Record<string, string> = {
    success: 'ico-box-success',
    warning: 'ico-box-warning',
    danger: 'ico-box-danger',
    info: '',
};

export default function Dashboard({ company, metrics, series, events, limits, plan, expiring, drafts }: Props) {
    const { auth } = usePage<SharedProps>().props;
    const verified = Boolean(auth?.user?.email_verified);
    const firstName = auth?.user?.name?.split(' ')[0] ?? '';

    if (!company) {
        return (
            <CabinetLayout title="Кабинет" heading={`Здравствуйте, ${firstName}`.trim()}>
                <div className="card empty">
                    <div className="empty-icon">
                        <Building2 aria-hidden className="size-7" />
                    </div>
                    <p className="t-h4">Компания ещё не создана</p>
                    <p className="t-sm muted mt-8" style={{ maxWidth: 460, margin: '8px auto 0' }}>
                        Пока карточки нет, объявления публиковать нельзя: покупатель должен видеть, с кем имеет дело.
                        Заполнение занимает пять минут.
                    </p>
                    <Link href={routes.cabinetCompany} className="btn btn-primary mt-24">
                        Заполнить данные компании
                    </Link>
                </div>
            </CabinetLayout>
        );
    }

    const incomplete = company.completeness < 100;

    return (
        <CabinetLayout
            title="Кабинет"
            heading={`Здравствуйте, ${firstName}`.trim()}
            subheading={
                <>
                    {company.name}
                    {plan && ` · тариф ${plan.name}`}
                    {plan?.until && ` до ${plan.until}`}
                </>
            }
            actions={
                <Link
                    href={routes.listingCreate}
                    className={cn('btn btn-primary', !verified && 'is-disabled')}
                    aria-disabled={!verified || undefined}
                    title={verified ? undefined : 'Сначала подтвердите почту'}
                >
                    <Plus aria-hidden className="size-4" /> Разместить объявление
                </Link>
            }
        >
            {/* Незаполненный профиль вредит конверсии сильнее, чем кажется:
                покупатель не звонит компании без адреса и документов */}
            {incomplete && (
                <div className="card" style={{ background: 'var(--warning-bg)', borderColor: 'rgba(245,158,11,.3)', marginBottom: 24 }}>
                    <div className="row-between wrap" style={{ gap: 16 }}>
                        <div style={{ flex: 1, minWidth: 260 }}>
                            <b>Профиль заполнен на {company.completeness} %</b>
                            <div className="progress mt-8" style={{ maxWidth: 340 }}>
                                <div className="progress-fill" style={{ width: `${company.completeness}%`, background: 'var(--warning)' }} />
                            </div>
                            {company.missing.length > 0 && (
                                <p className="t-sm mt-8" style={{ color: '#78350F' }}>
                                    Не хватает: {company.missing.join(', ')}.
                                </p>
                            )}
                        </div>
                        <Link href={routes.cabinetCompany} className="btn btn-secondary">
                            Дозаполнить
                        </Link>
                    </div>
                </div>
            )}

            {metrics && series && (
                <div className="grid grid-4 grid-tight">
                    <Metric label="Показы в выдаче" data={metrics.impressions} series={series.impressions} />
                    <Metric label="Просмотры карточек" data={metrics.views} series={series.views} />
                    <Metric label="Открыли ваш контакт" data={metrics.unlocks} series={series.unlocks} />
                    <Metric label="Конверсия в контакт" data={metrics.conversion} />
                </div>
            )}

            <div className="grid grid-split mt-24" style={{ ['--split' as string]: '1.4fr 1fr' }}>
                <Panel
                    title="Последние события"
                    action={
                        <Link href={routes.cabinetIncoming} className="t-sm">
                            Все события
                        </Link>
                    }
                >
                    {events.length === 0 ? (
                        <p className="muted t-sm">
                            Пока пусто. События появятся, когда объявления начнут смотреть и открывать контакты.
                        </p>
                    ) : (
                        <ul className="stack-16">
                            {events.map((e) => {
                                const Icon = EVENT_ICONS[e.type] ?? Eye;
                                return (
                                    <li key={e.id} className="row" style={{ gap: 12, alignItems: 'flex-start' }}>
                                        <span className={cn('ico-box ico-box-sm', TONE_CLASS[e.tone])}>
                                            <Icon aria-hidden className="size-4" />
                                        </span>
                                        <span className="t-sm" style={{ flex: 1 }}>
                                            {e.message}
                                            <br />
                                            <span className="muted t-caption">{e.ago}</span>
                                        </span>
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </Panel>

                {limits && plan && (
                    <Panel title={`Лимиты тарифа ${plan.name}`}>
                        <div className="stack-16">
                            <LimitBar label="Объявления" used={limits.listings.used} total={limits.listings.total} />
                            <LimitBar
                                label="Контакты в этом месяце"
                                used={limits.contacts.used}
                                total={limits.contacts.total}
                            />
                            <LimitBar label="Продвижения" used={limits.promo.used} total={limits.promo.total} />
                        </div>
                        {limits.resets_at && <p className="t-sm muted mt-16">Обновится {limits.resets_at}</p>}
                        <Link href={routes.cabinetBilling} className="btn btn-secondary btn-block mt-16">
                            Управление тарифом
                        </Link>
                    </Panel>
                )}
            </div>

            {(expiring > 0 || drafts > 0) && (
                <div className="grid grid-2 mt-24">
                    {expiring > 0 && (
                        <div className="alert alert-warning">
                            <TriangleAlert aria-hidden className="size-5" />
                            <div>
                                <b>{pluralize(expiring, ['объявление истекает', 'объявления истекают', 'объявлений истекает'])}</b>{' '}
                                в ближайшую неделю. После истечения показы прекращаются.{' '}
                                <Link href={routes.cabinetListings}>Проверить</Link>
                            </div>
                        </div>
                    )}
                    {drafts > 0 && (
                        <div className="alert alert-info">
                            <FileText aria-hidden className="size-5" />
                            <div>
                                Черновиков: <b>{drafts}</b>. Они не видны покупателям, пока не опубликованы.{' '}
                                <Link href={routes.cabinetListings}>Открыть</Link>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </CabinetLayout>
    );
}
