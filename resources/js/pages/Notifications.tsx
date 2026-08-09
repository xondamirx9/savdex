import { router } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import {
    Bell,
    CheckCheck,
    CreditCard,
    Clock,
    Eye,
    FileText,
    Megaphone,
    Star,
} from 'lucide-react';
import type { ComponentType } from 'react';
import { Tabs } from '@/components/cabinet';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { cn } from '@/lib/cn';
import { pluralize } from '@/lib/plural';
import { routes } from '@/routes';

interface Row {
    id: number;
    type: string;
    tone: string;
    title: string;
    body: string | null;
    url: string | null;
    is_broadcast: boolean;
    read: boolean;
    ago: string;
    date: string;
}

const ICONS: Record<string, ComponentType<{ className?: string; 'aria-hidden'?: boolean }>> = {
    contact_unlocked: Eye,
    new_review: Star,
    moderation: FileText,
    listing_expiring: Clock,
    payment: CreditCard,
    promotion: Megaphone,
    broadcast: Bell,
};

const TONE_BOX: Record<string, string> = {
    success: 'ico-box-success',
    warning: 'ico-box-warning',
    danger: 'ico-box-danger',
    info: '',
};

export default function Notifications({
    notifications,
    filter,
    unread,
}: {
    notifications: Row[];
    filter: 'all' | 'unread';
    unread: number;
}) {
    return (
        <CabinetLayout
            title="Уведомления"
            heading="Уведомления"
            subheading={
                unread > 0
                    ? `${pluralize(unread, ['непрочитанное', 'непрочитанных', 'непрочитанных'])}`
                    : 'Все прочитаны'
            }
            actions={
                unread > 0 ? (
                    <button
                        className="btn btn-secondary"
                        onClick={() => router.post(routes.notificationsReadAll, {}, { preserveScroll: true })}
                    >
                        <CheckCheck aria-hidden className="size-4" /> Отметить всё прочитанным
                    </button>
                ) : undefined
            }
        >
            <Tabs
                items={[
                    { key: 'all', label: 'Все' },
                    { key: 'unread', label: 'Непрочитанные', count: unread },
                ]}
                active={filter}
                onChange={(key) =>
                    router.get(routes.notifications, key === 'unread' ? { filter: 'unread' } : {}, {
                        preserveState: true,
                        replace: true,
                    })
                }
                label="Фильтр уведомлений"
            />

            {notifications.length === 0 ? (
                <div className="card empty">
                    <div className="empty-icon">
                        <Bell aria-hidden className="size-7" />
                    </div>
                    <p className="t-h4">{filter === 'unread' ? 'Непрочитанных нет' : 'Уведомлений пока нет'}</p>
                    <p className="t-sm muted mt-8" style={{ maxWidth: 420, margin: '8px auto 0' }}>
                        Здесь появятся отклики на объявления, новые отзывы, результаты модерации и новости площадки.
                    </p>
                </div>
            ) : (
                <div className="stack-12">
                    {notifications.map((n) => {
                        const Icon = ICONS[n.type] ?? Bell;

                        const inner = (
                            <>
                                <span className={cn('ico-box ico-box-sm shrink-0', TONE_BOX[n.tone])}>
                                    <Icon aria-hidden className="size-4" />
                                </span>
                                <span style={{ flex: 1, minWidth: 0 }}>
                                    <span className="row wrap" style={{ gap: 8 }}>
                                        <b className={cn(!n.read && 'notif-strong')}>{n.title}</b>
                                        {n.is_broadcast && <span className="badge badge-neutral">от площадки</span>}
                                    </span>
                                    {n.body && <p className="t-sm muted mt-8">{n.body}</p>}
                                    <span className="t-caption muted" title={n.date}>
                                        {n.ago}
                                    </span>
                                </span>
                                {!n.read && <span className="notif-dot-static" aria-label="Непрочитано" />}
                            </>
                        );

                        // Уведомление без ссылки не делаем кнопкой: нажатие,
                        // которое никуда не ведёт, читается как поломка
                        return n.url ? (
                            <Link
                                key={n.id}
                                href={routes.notificationRead(n.id)}
                                method="post"
                                as="button"
                                className={cn('card notif-row', !n.read && 'is-unread')}
                            >
                                {inner}
                            </Link>
                        ) : (
                            <div key={n.id} className={cn('card notif-row', !n.read && 'is-unread')}>
                                {inner}
                            </div>
                        );
                    })}
                </div>
            )}
        </CabinetLayout>
    );
}
