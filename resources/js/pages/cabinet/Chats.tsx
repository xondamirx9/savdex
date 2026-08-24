import { Link } from '@/components/ui/Link';
import { MessageSquareText } from 'lucide-react';
import { Panel } from '@/components/cabinet';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { routes } from '@/routes';

interface ThreadRow {
    id: number;
    company: string;
    initials: string;
    listing: string | null;
    last: string | null;
    last_mine: boolean;
    at: string | null;
    unread: number;
}

/**
 * Список разговоров: покупательские и продавецкие вперемешку,
 * свежие сверху. Непрочитанное выделяется жирным и счётчиком —
 * как в любом привычном мессенджере, ничего изобретать не нужно.
 */
export default function Chats({ threads, hasCompany }: { threads: ThreadRow[]; hasCompany: boolean }) {
    return (
        <CabinetLayout title="Чаты" heading="Чаты" subheading="Отклики на объявления и переписка с компаниями">
            {!hasCompany ? (
                <Panel>
                    <p className="muted">Заполните данные компании — переписка на площадке ведётся от её имени.</p>
                </Panel>
            ) : threads.length === 0 ? (
                <Panel>
                    <div className="stack-8" style={{ textAlign: 'center', padding: '24px 0' }}>
                        <MessageSquareText aria-hidden className="size-8" style={{ margin: '0 auto', color: 'var(--text-muted)' }} />
                        <p className="muted">
                            Пока пусто. Найдите товар в каталоге и нажмите «Откликнуться» — разговор появится здесь.
                            Отклики на ваши объявления тоже приходят сюда.
                        </p>
                        <p>
                            <Link href={routes.catalog} className="btn btn-secondary btn-sm">
                                Открыть каталог
                            </Link>
                        </p>
                    </div>
                </Panel>
            ) : (
                <div className="stack-8">
                    {threads.map((thread) => (
                        <Link key={thread.id} href={routes.cabinetChat(thread.id)} className="card lift chat-row">
                            <span className="listing-logo logo-48">{thread.initials}</span>
                            <div style={{ minWidth: 0, flex: 1 }}>
                                <div className="row-between" style={{ gap: 12 }}>
                                    <b className="truncate">{thread.company}</b>
                                    <span className="t-caption muted" style={{ flexShrink: 0 }}>
                                        {thread.at}
                                    </span>
                                </div>
                                {thread.listing && <p className="t-caption muted truncate">{thread.listing}</p>}
                                {thread.last && (
                                    <p
                                        className="t-sm truncate"
                                        style={{ fontWeight: thread.unread > 0 ? 600 : 400 }}
                                    >
                                        {thread.last_mine ? 'Вы: ' : ''}
                                        {thread.last}
                                    </p>
                                )}
                            </div>
                            {thread.unread > 0 && <span className="hd-badge chat-unread">{thread.unread}</span>}
                        </Link>
                    ))}
                </div>
            )}
        </CabinetLayout>
    );
}
