import { router, useForm } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { CheckCircle2, Code2, Eye, ExternalLink, MessageSquareText, Paperclip, Pencil, Plus } from 'lucide-react';
import { useState } from 'react';
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
    status: 'active' | 'closed' | 'completed' | 'archived';
    status_label: string;
    responses: number;
    views: number;
    files: number;
    published: string | null;
    result_url: string | null;
    result_summary: string | null;
    contractor: string | null;
    responders: { id: number; name: string }[];
}

const STATUS_BADGE: Record<Row['status'], string> = {
    active: 'badge-verified',
    closed: 'badge-neutral',
    completed: 'badge-supply',
    archived: 'badge-neutral',
};

/**
 * Форма «Выполнена»: ссылка на результат, что сделано и кто сделал.
 * Исполнитель — только из откликнувшихся, так витрина не превращается
 * в бесплатную рекламу произвольных компаний.
 */
function CompleteForm({ task, onDone }: { task: Row; onDone: () => void }) {
    const form = useForm<{ result_url: string; result_summary: string; contractor_company_id: string }>({
        result_url: '',
        result_summary: '',
        contractor_company_id: '',
    });

    function submit(e: React.FormEvent) {
        e.preventDefault();
        form.post(routes.itTaskComplete(task.id), { preserveScroll: true, onSuccess: onDone });
    }

    return (
        <form onSubmit={submit} style={{ display: 'grid', gap: 10, paddingTop: 12, borderTop: '1px solid var(--border)' }}>
            <div className="field" style={{ margin: 0 }}>
                <label className="label" htmlFor={`r-url-${task.id}`}>Ссылка на результат</label>
                <input
                    id={`r-url-${task.id}`}
                    className="input"
                    placeholder="https://…"
                    value={form.data.result_url}
                    onChange={(e) => form.setData('result_url', e.target.value)}
                />
                {form.errors.result_url && <p className="hint" style={{ color: 'var(--danger)' }}>{form.errors.result_url}</p>}
            </div>
            <div className="field" style={{ margin: 0 }}>
                <label className="label" htmlFor={`r-sum-${task.id}`}>Что сделано</label>
                <textarea
                    id={`r-sum-${task.id}`}
                    className="input"
                    rows={3}
                    maxLength={600}
                    placeholder="Коротко: что получилось в итоге — это увидят другие заказчики"
                    value={form.data.result_summary}
                    onChange={(e) => form.setData('result_summary', e.target.value)}
                />
            </div>
            <div className="field" style={{ margin: 0 }}>
                <label className="label" htmlFor={`r-who-${task.id}`}>Исполнитель</label>
                <select
                    id={`r-who-${task.id}`}
                    className="select"
                    value={form.data.contractor_company_id}
                    onChange={(e) => form.setData('contractor_company_id', e.target.value)}
                >
                    <option value="">Не указывать</option>
                    {task.responders.map((r) => (
                        <option key={r.id} value={r.id}>
                            {r.name}
                        </option>
                    ))}
                </select>
                {form.errors.contractor_company_id && (
                    <p className="hint" style={{ color: 'var(--danger)' }}>{form.errors.contractor_company_id}</p>
                )}
                {task.responders.length === 0 && <p className="hint">Откликов пока не было — исполнителя можно не указывать.</p>}
            </div>
            <div className="row" style={{ gap: 8 }}>
                <button type="submit" className="btn btn-primary btn-sm" disabled={form.processing}>
                    <CheckCircle2 aria-hidden className="size-4" /> Отметить выполненной
                </button>
                <button type="button" className="btn btn-ghost btn-sm" onClick={onDone}>
                    Отмена
                </button>
            </div>
        </form>
    );
}

export default function ItTasksIndex({ tasks, hasCompany }: { tasks: Row[]; hasCompany: boolean }) {
    const { confirm, dialog } = useConfirm();
    const [completing, setCompleting] = useState<number | null>(null);

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
                                    {t.status !== 'completed' && (
                                        <button
                                            type="button"
                                            className="btn btn-secondary btn-sm"
                                            onClick={() => setCompleting(completing === t.id ? null : t.id)}
                                        >
                                            <CheckCircle2 aria-hidden className="size-4" /> Выполнена
                                        </button>
                                    )}
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
                                    ) : t.status !== 'completed' ? (
                                        <button
                                            type="button"
                                            className="btn btn-ghost btn-sm"
                                            onClick={() => router.post(routes.itTaskReopen(t.id), {}, { preserveScroll: true })}
                                        >
                                            Открыть снова
                                        </button>
                                    ) : null}
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

                            {t.status === 'completed' && (
                                <div className="t-sm" style={{ display: 'grid', gap: 4 }}>
                                    {t.result_summary && <p>{t.result_summary}</p>}
                                    <div className="row wrap muted" style={{ gap: 12 }}>
                                        {t.result_url && (
                                            <a href={t.result_url} target="_blank" rel="noopener noreferrer" className="row" style={{ gap: 4 }}>
                                                <ExternalLink aria-hidden className="size-4" /> {t.result_url.replace(/^https?:\/\/(www\.)?/, '')}
                                            </a>
                                        )}
                                        {t.contractor && <span>Исполнитель: {t.contractor}</span>}
                                    </div>
                                </div>
                            )}

                            {completing === t.id && <CompleteForm task={t} onDone={() => setCompleting(null)} />}
                        </div>
                    ))}
                </div>
            )}
        </CabinetLayout>
    );
}
