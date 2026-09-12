import { router } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { Code2, Eye, MessageSquareText, Paperclip, Pencil, Plus } from 'lucide-react';
import { Empty } from '@/components/cabinet';
import { useConfirm } from '@/components/useConfirm';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { routes } from '@/routes';

interface Row {
    id: number;
    slug: string | null;
    title: string;
    service_type: string;
    budget: string;
    deadline: string | null;
    status: 'active' | 'closed' | 'archived';
    status_label: string;
    responses: number;
    views: number;
    files: number;
    published: string | null;
}

const STATUS_BADGE: Record<Row['status'], string> = {
    active: 'badge-verified',
    closed: 'badge-neutral',
    archived: 'badge-neutral',
};

export default function ItTasksIndex({ tasks, hasCompany }: { tasks: Row[]; hasCompany: boolean }) {
    const { confirm, dialog } = useConfirm();

    return (
        <CabinetLayout
            title="IT-задачи"
            heading="IT-задачи"
            subheading="Опишите, что нужно разработать или настроить, — IT-команды площадки откликнутся в чат"
            actions={
                hasCompany ? (
                    <Link href={routes.itTaskCreate} className="btn btn-primary btn-sm">
                        <Plus aria-hidden className="size-4" /> Новая задача
                    </Link>
                ) : undefined
            }
        >
            {dialog}

            {!hasCompany ? (
                <Empty
                    icon={Code2}
                    title="Сначала заполните данные компании"
                    text="IT-задача публикуется от имени компании — исполнители должны видеть, с кем будут работать."
                    action={{ href: routes.cabinetCompany, label: 'Заполнить профиль' }}
                />
            ) : tasks.length === 0 ? (
                <Empty
                    icon={Code2}
                    title="IT-задач пока нет"
                    text="Сайт, мобильное приложение, интеграция с 1С, бот для заявок — опишите задачу, и исполнители сами придут в чат."
                    action={{ href: routes.itTaskCreate, label: 'Опубликовать задачу' }}
                />
            ) : (
                <div style={{ display: 'grid', gap: 12 }}>
                    {tasks.map((t) => (
                        <div key={t.id} className="card" style={{ display: 'grid', gap: 10 }}>
                            <div className="row wrap" style={{ gap: 8, justifyContent: 'space-between' }}>
                                <div className="row wrap" style={{ gap: 8 }}>
                                    <span className={`badge ${STATUS_BADGE[t.status]}`}>{t.status_label}</span>
                                    <span className="badge badge-neutral">{t.service_type}</span>
                                    {t.published && <span className="t-caption muted">{t.published}</span>}
                                </div>
                                <div className="row" style={{ gap: 6 }}>
                                    {t.status === 'active' && t.slug && (
                                        <Link href={routes.itTask(t.slug)} className="btn btn-ghost btn-sm">
                                            <Eye aria-hidden className="size-4" /> На сайте
                                        </Link>
                                    )}
                                    <Link href={routes.itTaskEdit(t.id)} className="btn btn-secondary btn-sm">
                                        <Pencil aria-hidden className="size-4" /> Изменить
                                    </Link>
                                    {t.status === 'active' ? (
                                        <button
                                            type="button"
                                            className="btn btn-ghost btn-sm"
                                            onClick={() =>
                                                confirm({
                                                    title: 'Закрыть задачу?',
                                                    description: 'Задача уйдёт с витрины, новые отклики перестанут приходить. Чаты с исполнителями останутся.',
                                                    confirmLabel: 'Закрыть',
                                                    onConfirm: () => router.post(routes.itTaskClose(t.id), {}, { preserveScroll: true }),
                                                })
                                            }
                                        >
                                            Закрыть
                                        </button>
                                    ) : (
                                        <button
                                            type="button"
                                            className="btn btn-ghost btn-sm"
                                            onClick={() => router.post(routes.itTaskReopen(t.id), {}, { preserveScroll: true })}
                                        >
                                            Открыть снова
                                        </button>
                                    )}
                                </div>
                            </div>

                            <h3 className="t-h4">{t.title}</h3>

                            <div className="row wrap t-sm muted" style={{ gap: 16 }}>
                                <span>Бюджет: <b style={{ color: 'var(--text)' }}>{t.budget}</b></span>
                                {t.deadline && <span>Срок: {t.deadline}</span>}
                                <span className="row" style={{ gap: 4 }}>
                                    <MessageSquareText aria-hidden className="size-4" /> {t.responses}
                                </span>
                                <span className="row" style={{ gap: 4 }}>
                                    <Eye aria-hidden className="size-4" /> {t.views}
                                </span>
                                {t.files > 0 && (
                                    <span className="row" style={{ gap: 4 }}>
                                        <Paperclip aria-hidden className="size-4" /> {t.files}
                                    </span>
                                )}
                            </div>
                        </div>
                    ))}
                </div>
            )}
        </CabinetLayout>
    );
}
