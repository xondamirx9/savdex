import { useForm } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { ArrowLeft, Building2, CalendarDays, CheckCircle2, Code2, ExternalLink, Eye, MessageSquareText, Paperclip, Wallet } from 'lucide-react';
import { useState } from 'react';
import { PublicLayout } from '@/layouts/PublicLayout';
import { t, tChoice } from '@/lib/i18n';
import { routes } from '@/routes';
import { budgetLabel, TaskCard, type TaskRow } from './Index';

interface Task extends TaskRow {
    description: string[];
    files: { id: number; title: string; size: string; ext: string }[];
    views: number;
}

interface Respond {
    guest: boolean;
    owner: boolean;
    no_company: boolean;
    provider: boolean;
}

/**
 * Карточка отклика: гостю — вход, компании без роли исполнителя —
 * объяснение и ссылка в профиль, исполнителю — форма. Заказчику
 * своей задачи карточка не показывается.
 */
function RespondCard({ taskId, respond }: { taskId: number; respond: Respond }) {
    const [open, setOpen] = useState(false);
    const form = useForm({ body: '' });

    if (respond.owner) return null;

    if (respond.guest) {
        return (
            <div className="card" style={{ display: 'grid', gap: 10 }}>
                <p className="t-sm muted">{t('it_tasks.respond_login')}</p>
                <Link href={routes.login} className="btn btn-primary">
                    {t('it_tasks.respond')}
                </Link>
            </div>
        );
    }

    if (respond.no_company || !respond.provider) {
        return (
            <div className="card" style={{ display: 'grid', gap: 10 }}>
                <p className="t-sm muted">
                    {respond.no_company ? t('it_tasks.respond_no_company') : t('it_tasks.respond_not_provider')}
                </p>
                <Link href={routes.cabinetCompany} className="btn btn-secondary">
                    {t('it_tasks.respond_become')}
                </Link>
            </div>
        );
    }

    function submit(e: React.FormEvent) {
        e.preventDefault();
        form.post(routes.itTaskRespond(taskId), { preserveScroll: true });
    }

    return (
        <div className="card" style={{ display: 'grid', gap: 10 }}>
            {!open ? (
                <>
                    <p className="t-sm muted">{t('it_tasks.respond_hint')}</p>
                    <button type="button" className="btn btn-primary" onClick={() => setOpen(true)}>
                        <MessageSquareText aria-hidden className="size-4" /> {t('it_tasks.respond')}
                    </button>
                </>
            ) : (
                <form onSubmit={submit} style={{ display: 'grid', gap: 10 }}>
                    <label htmlFor="it-respond" className="sr-only">
                        {t('it_tasks.respond')}
                    </label>
                    <textarea
                        id="it-respond"
                        className="input"
                        rows={5}
                        maxLength={2000}
                        placeholder={t('it_tasks.respond_placeholder')}
                        value={form.data.body}
                        onChange={(e) => form.setData('body', e.target.value)}
                        autoFocus
                    />
                    {form.errors.body && (
                        <p className="t-sm" style={{ color: 'var(--danger)' }}>
                            {form.errors.body}
                        </p>
                    )}
                    <button type="submit" className="btn btn-primary" disabled={form.processing || !form.data.body.trim()}>
                        {form.processing ? t('it_tasks.respond_sending') : t('it_tasks.respond_send')}
                    </button>
                    <p className="t-caption muted">{t('it_tasks.respond_note')}</p>
                </form>
            )}
        </div>
    );
}

export default function ItTaskShow({ task, respond, similar }: { task: Task; respond: Respond; similar: TaskRow[] }) {
    return (
        <PublicLayout title={task.title} description={task.excerpt}>
            <div className="container" style={{ padding: '24px 0 96px' }}>
                <nav aria-label={t('it_tasks.breadcrumbs')} style={{ paddingBottom: 20 }}>
                    <ol className="row t-sm muted" style={{ gap: 8, flexWrap: 'wrap' }}>
                        <li>
                            <Link href={routes.home}>{t('it_tasks.home')}</Link>
                        </li>
                        <li aria-hidden="true">/</li>
                        <li>
                            <Link href={routes.itTasks}>{t('it_tasks.h1')}</Link>
                        </li>
                        <li aria-hidden="true">/</li>
                        <li aria-current="page" style={{ color: 'var(--text)' }}>
                            {task.service_label}
                        </li>
                    </ol>
                </nav>

                <div className="grid" style={{ gridTemplateColumns: 'minmax(0, 1fr) 340px', gap: 32, alignItems: 'start' }}>
                    <article style={{ maxWidth: '72ch' }}>
                        <div className="row wrap" style={{ gap: 10, marginBottom: 16 }}>
                            <span className="badge badge-supply">{task.service_label}</span>
                            {task.completed ? (
                                <span className="badge badge-verified">
                                    <CheckCircle2 aria-hidden className="size-3.5" /> {t('it_tasks.completed')}
                                </span>
                            ) : (
                                !task.active && <span className="badge badge-neutral">{t('it_tasks.closed')}</span>
                            )}
                            {task.published && (
                                <span className="t-caption muted row" style={{ gap: 6 }}>
                                    <CalendarDays aria-hidden className="size-3.5" /> {t('it_tasks.published')}: {task.published}
                                </span>
                            )}
                            <span className="t-caption muted row" style={{ gap: 6 }}>
                                <Eye aria-hidden className="size-3.5" /> {task.views}
                            </span>
                        </div>

                        <h1 className="t-h1">{task.title}</h1>

                        {task.stack.length > 0 && (
                            <div className="row wrap mt-16" style={{ gap: 6 }}>
                                {task.stack.map((s) => (
                                    <span key={s} className="chip" style={{ cursor: 'default' }}>{s}</span>
                                ))}
                            </div>
                        )}

                        {task.completed && (
                            <section className="card mt-24" style={{ display: 'grid', gap: 10, background: 'var(--primary-50, #eef4ff)' }}>
                                <h2 className="t-h4 row" style={{ gap: 8 }}>
                                    <CheckCircle2 aria-hidden className="size-5" style={{ color: 'var(--success)' }} /> {t('it_tasks.result')}
                                    {task.completed_on && <span className="t-caption muted">· {task.completed_on}</span>}
                                </h2>
                                {task.result_summary && <p className="t-body">{task.result_summary}</p>}
                                {task.result_url && (
                                    <a
                                        href={task.result_url}
                                        target="_blank"
                                        rel="noopener noreferrer nofollow"
                                        className="btn btn-primary"
                                        style={{ justifySelf: 'start' }}
                                    >
                                        <ExternalLink aria-hidden className="size-4" /> {t('it_tasks.result_open')}
                                        {task.result_host && <span className="muted"> · {task.result_host}</span>}
                                    </a>
                                )}
                                {task.contractor && (
                                    <Link href={routes.company(task.contractor.slug)} className="row" style={{ gap: 10, color: 'inherit' }}>
                                        <span className="listing-logo logo-48">
                                            {task.contractor.logo ? <img src={task.contractor.logo} alt="" /> : task.contractor.initials}
                                        </span>
                                        <span>
                                            <span className="t-caption muted">{t('it_tasks.contractor')}</span>
                                            <span className="t-body row" style={{ gap: 6 }}>
                                                <Code2 aria-hidden className="size-4 muted" /> {task.contractor.name}
                                            </span>
                                        </span>
                                    </Link>
                                )}
                            </section>
                        )}

                        <div className="mt-32">
                            {task.description.map((p, i) => (
                                <p key={i} className="t-body" style={{ marginBottom: 18 }}>
                                    {p}
                                </p>
                            ))}
                        </div>

                        {task.files.length > 0 && (
                            <section className="mt-32">
                                <h2 className="t-h4" style={{ marginBottom: 12 }}>
                                    {t('it_tasks.files')}
                                </h2>
                                {respond.guest ? (
                                    <p className="t-sm muted">
                                        <Link href={routes.login}>{t('it_tasks.files_login')}</Link>
                                    </p>
                                ) : (
                                    <ul style={{ display: 'grid', gap: 8, padding: 0, listStyle: 'none' }}>
                                        {task.files.map((f) => (
                                            <li key={f.id}>
                                                <a href={routes.itTaskFile(f.id)} className="row t-sm" style={{ gap: 8 }}>
                                                    <Paperclip aria-hidden className="size-4 muted" />
                                                    {f.title} <span className="muted">· {f.size}</span>
                                                </a>
                                            </li>
                                        ))}
                                    </ul>
                                )}
                            </section>
                        )}

                        <div className="mt-48" style={{ paddingTop: 24, borderTop: '1px solid var(--border)' }}>
                            <Link href={routes.itTasks} className="btn btn-secondary">
                                <ArrowLeft aria-hidden className="size-4" /> {t('it_tasks.back')}
                            </Link>
                        </div>
                    </article>

                    <div style={{ display: 'grid', gap: 16 }}>
                        <aside className="card" style={{ display: 'grid', gap: 16 }}>
                            <div>
                                <div className="t-caption muted">{t('it_tasks.budget')}</div>
                                <div className="t-h3 row" style={{ gap: 8 }}>
                                    <Wallet aria-hidden className="size-5 muted" /> {budgetLabel(task)}
                                </div>
                            </div>
                            <div>
                                <div className="t-caption muted">{t('it_tasks.deadline')}</div>
                                <div className="t-body row" style={{ gap: 8 }}>
                                    <CalendarDays aria-hidden className="size-4 muted" />
                                    {task.deadline ?? t('it_tasks.deadline_none')}
                                </div>
                            </div>
                            {task.company && (
                                <div>
                                    <div className="t-caption muted">{t('it_tasks.customer')}</div>
                                    <Link href={routes.company(task.company.slug)} className="row" style={{ gap: 10, color: 'inherit' }}>
                                        <span className="listing-logo logo-48">
                                            {task.company.logo ? <img src={task.company.logo} alt="" /> : task.company.initials}
                                        </span>
                                        <span>
                                            <span className="t-body row" style={{ gap: 6 }}>
                                                <Building2 aria-hidden className="size-4 muted" /> {task.company.name}
                                                {task.company.verified && <CheckCircle2 aria-hidden className="size-4" style={{ color: 'var(--success)' }} />}
                                            </span>
                                            {task.company.city && <span className="t-caption muted">{task.company.city}</span>}
                                        </span>
                                    </Link>
                                </div>
                            )}
                            <div className="t-sm muted row" style={{ gap: 6 }}>
                                <MessageSquareText aria-hidden className="size-4" /> {tChoice('it_tasks.responses', task.responses)}
                            </div>
                        </aside>

                        {task.active && <RespondCard taskId={task.id} respond={respond} />}
                    </div>
                </div>

                {similar.length > 0 && (
                    <section className="mt-48">
                        <h2 className="t-h3" style={{ marginBottom: 20 }}>
                            {t('it_tasks.similar')}
                        </h2>
                        <div className="grid grid-3">
                            {similar.map((row) => (
                                <TaskCard key={row.id} row={row} />
                            ))}
                        </div>
                    </section>
                )}
            </div>
        </PublicLayout>
    );
}
