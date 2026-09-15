import { router, useForm } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { CheckCircle2, Code2, Eye, ExternalLink, MessageSquareText, Paperclip, Pencil, Plus } from 'lucide-react';
import { useState } from 'react';
import { Empty } from '@/components/cabinet';
import { useConfirm } from '@/components/useConfirm';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { routes } from '@/routes';
import { t } from '@/lib/i18n';

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
                <label className="label" htmlFor={`r-url-${task.id}`}>{t('cabinet.it_tasks.result_url')}</label>
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
                <label className="label" htmlFor={`r-sum-${task.id}`}>{t('cabinet.it_tasks.result_summary')}</label>
                <textarea
                    id={`r-sum-${task.id}`}
                    className="input"
                    rows={3}
                    maxLength={600}
                    placeholder={t('cabinet.it_tasks.result_summary_placeholder')}
                    value={form.data.result_summary}
                    onChange={(e) => form.setData('result_summary', e.target.value)}
                />
            </div>
            <div className="field" style={{ margin: 0 }}>
                <label className="label" htmlFor={`r-who-${task.id}`}>{t('cabinet.it_tasks.contractor')}</label>
                <select
                    id={`r-who-${task.id}`}
                    className="select"
                    value={form.data.contractor_company_id}
                    onChange={(e) => form.setData('contractor_company_id', e.target.value)}
                >
                    <option value="">{t('cabinet.it_tasks.contractor_none')}</option>
                    {task.responders.map((r) => (
                        <option key={r.id} value={r.id}>
                            {r.name}
                        </option>
                    ))}
                </select>
                {form.errors.contractor_company_id && (
                    <p className="hint" style={{ color: 'var(--danger)' }}>{form.errors.contractor_company_id}</p>
                )}
                {task.responders.length === 0 && <p className="hint">{t('cabinet.it_tasks.no_responders')}</p>}
            </div>
            <div className="row" style={{ gap: 8 }}>
                <button type="submit" className="btn btn-primary btn-sm" disabled={form.processing}>
                    <CheckCircle2 aria-hidden className="size-4" /> {t('cabinet.it_tasks.mark_done')}
                </button>
                <button type="button" className="btn btn-ghost btn-sm" onClick={onDone}>
                    {t('common.cancel')}
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
            title={t('cabinet.it_tasks.title')}
            heading={t('cabinet.it_tasks.title')}
            subheading={t('cabinet.it_tasks.subtitle')}
            actions={
                hasCompany ? (
                    <Link href={routes.itTaskCreate} className="btn btn-primary btn-sm">
                        <Plus aria-hidden className="size-4" /> {t('cabinet.it_tasks.new')}
                    </Link>
                ) : undefined
            }
        >
            {dialog}

            {!hasCompany ? (
                <Empty
                    icon={Code2}
                    title={t('cabinet.it_tasks.no_company')}
                    text={t('cabinet.it_tasks.no_company_text')}
                    action={{ href: routes.cabinetCompany, label: t('cabinet.it_tasks.fill_profile') }}
                />
            ) : tasks.length === 0 ? (
                <Empty
                    icon={Code2}
                    title={t('cabinet.it_tasks.empty')}
                    text={t('cabinet.it_tasks.empty_text')}
                    action={{ href: routes.itTaskCreate, label: t('cabinet.it_tasks.publish') }}
                />
            ) : (
                <div style={{ display: 'grid', gap: 12 }}>
                    {tasks.map((task) => (
                        <div key={task.id} className="card" style={{ display: 'grid', gap: 10 }}>
                            <div className="row wrap" style={{ gap: 8, justifyContent: 'space-between' }}>
                                <div className="row wrap" style={{ gap: 8 }}>
                                    <span className={`badge ${STATUS_BADGE[task.status]}`}>{task.status_label}</span>
                                    <span className="badge badge-neutral">{task.service_type}</span>
                                    {task.published && <span className="t-caption muted">{task.published}</span>}
                                </div>
                                <div className="row" style={{ gap: 6 }}>
                                    {task.status === 'active' && task.slug && (
                                        <Link href={routes.itTask(task.slug)} className="btn btn-ghost btn-sm">
                                            <Eye aria-hidden className="size-4" /> {t('cabinet.it_tasks.on_site')}
                                        </Link>
                                    )}
                                    <Link href={routes.itTaskEdit(task.id)} className="btn btn-secondary btn-sm">
                                        <Pencil aria-hidden className="size-4" /> {t('common.edit')}
                                    </Link>
                                    {task.status !== 'completed' && (
                                        <button
                                            type="button"
                                            className="btn btn-secondary btn-sm"
                                            onClick={() => setCompleting(completing === task.id ? null : task.id)}
                                        >
                                            <CheckCircle2 aria-hidden className="size-4" /> {t('cabinet.it_tasks.done')}
                                        </button>
                                    )}
                                    {task.status === 'active' ? (
                                        <button
                                            type="button"
                                            className="btn btn-ghost btn-sm"
                                            onClick={() =>
                                                confirm({
                                                    title: t('cabinet.it_tasks.close_title'),
                                                    description: t('cabinet.it_tasks.close_text'),
                                                    confirmLabel: t('cabinet.it_tasks.close'),
                                                    onConfirm: () => router.post(routes.itTaskClose(task.id), {}, { preserveScroll: true }),
                                                })
                                            }
                                        >
                                            {t('cabinet.it_tasks.close')}
                                        </button>
                                    ) : task.status !== 'completed' ? (
                                        <button
                                            type="button"
                                            className="btn btn-ghost btn-sm"
                                            onClick={() => router.post(routes.itTaskReopen(task.id), {}, { preserveScroll: true })}
                                        >
                                            {t('cabinet.it_tasks.reopen')}
                                        </button>
                                    ) : null}
                                </div>
                            </div>

                            <h3 className="t-h4">{task.title}</h3>

                            <div className="row wrap t-sm muted" style={{ gap: 16 }}>
                                <span>
                                    {t('cabinet.it_tasks.budget')}{' '}
                                    <b style={{ color: 'var(--text)' }}>{task.budget}</b>
                                </span>
                                {task.deadline && (
                                    <span>{t('cabinet.it_tasks.deadline', { date: task.deadline })}</span>
                                )}
                                <span className="row" style={{ gap: 4 }}>
                                    <MessageSquareText aria-hidden className="size-4" /> {task.responses}
                                </span>
                                <span className="row" style={{ gap: 4 }}>
                                    <Eye aria-hidden className="size-4" /> {task.views}
                                </span>
                                {task.files > 0 && (
                                    <span className="row" style={{ gap: 4 }}>
                                        <Paperclip aria-hidden className="size-4" /> {task.files}
                                    </span>
                                )}
                            </div>

                            {task.status === 'completed' && (
                                <div className="t-sm" style={{ display: 'grid', gap: 4 }}>
                                    {task.result_summary && <p>{task.result_summary}</p>}
                                    <div className="row wrap muted" style={{ gap: 12 }}>
                                        {task.result_url && (
                                            <a href={task.result_url} target="_blank" rel="noopener noreferrer" className="row" style={{ gap: 4 }}>
                                                <ExternalLink aria-hidden className="size-4" /> {task.result_url.replace(/^https?:\/\/(www\.)?/, '')}
                                            </a>
                                        )}
                                        {task.contractor && (
                                            <span>{t('cabinet.it_tasks.by', { company: task.contractor })}</span>
                                        )}
                                    </div>
                                </div>
                            )}

                            {completing === task.id && <CompleteForm task={task} onDone={() => setCompleting(null)} />}
                        </div>
                    ))}
                </div>
            )}
        </CabinetLayout>
    );
}
