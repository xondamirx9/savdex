import { router, useForm } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { ArrowLeft, Paperclip, Trash2, X } from 'lucide-react';
import { useState } from 'react';
import { useConfirm } from '@/components/useConfirm';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { cn } from '@/lib/cn';
import { routes } from '@/routes';
import { t } from '@/lib/i18n';

interface Task {
    id: number;
    slug: string | null;
    title: string;
    description: string;
    service_type: string;
    stack: string[];
    budget_type: 'fixed' | 'range' | 'negotiable';
    budget_from: number | null;
    budget_to: number | null;
    currency: string;
    deadline_at: string | null;
    status: string;
}

interface Props {
    task: Task | null;
    files: { id: number; title: string; size: string }[];
    serviceTypes: Record<string, string>;
    currencies: string[];
}

const MAX_FILES = 5;

/**
 * Одна форма вместо мастера: полей меньше, чем у объявления, и каждое
 * понятно без подсказок. Файлы ТЗ уходят той же отправкой (multipart),
 * уже загруженные — списком с удалением.
 */
export default function ItTaskForm({ task, files, serviceTypes, currencies }: Props) {
    const { confirm, dialog } = useConfirm();
    const [tag, setTag] = useState('');

    const form = useForm<{
        title: string;
        description: string;
        service_type: string;
        stack: string[];
        budget_type: 'fixed' | 'range' | 'negotiable';
        budget_from: string;
        budget_to: string;
        currency: string;
        deadline_at: string;
        files: File[];
    }>({
        title: task?.title ?? '',
        description: task?.description ?? '',
        service_type: task?.service_type ?? 'web',
        stack: task?.stack ?? [],
        budget_type: task?.budget_type ?? 'negotiable',
        budget_from: task?.budget_from?.toString() ?? '',
        budget_to: task?.budget_to?.toString() ?? '',
        currency: task?.currency ?? 'UZS',
        deadline_at: task?.deadline_at ?? '',
        files: [],
    });

    function addTag() {
        const value = tag.trim();
        if (!value || form.data.stack.includes(value) || form.data.stack.length >= 10) return;
        form.setData('stack', [...form.data.stack, value]);
        setTag('');
    }

    function submit(e: React.FormEvent) {
        e.preventDefault();
        /* Inertia сама шлёт multipart, когда в данных есть File; PATCH
           с файлами браузер не умеет — используем POST с _method */
        if (task) {
            form.transform((data) => ({ ...data, _method: 'patch' }));
            form.post(routes.itTaskUpdate(task.id), { forceFormData: true, preserveScroll: true });
        } else {
            form.post('/cabinet/it-tasks', { forceFormData: true, preserveScroll: true });
        }
    }

    const err = (key: string) => (form.errors as Record<string, string | undefined>)[key];
    const roomForFiles = MAX_FILES - files.length;

    return (
        <CabinetLayout
            title={task ? t('cabinet.it_task_form.edit') : t('cabinet.it_task_form.create')}
            heading={task ? t('cabinet.it_task_form.edit') : t('cabinet.it_task_form.create')}
            subheading={t('cabinet.it_task_form.subtitle')}
            actions={
                <Link href={routes.cabinetItTasks} className="btn btn-secondary btn-sm">
                    <ArrowLeft aria-hidden className="size-4" /> {t('cabinet.it_task_form.all')}
                </Link>
            }
        >
            {dialog}

            <form onSubmit={submit} className="card" style={{ maxWidth: 760 }}>
                <div className="field">
                    <label className="label" htmlFor="t-title">
                        {t('cabinet.it_task_form.name')} <span className="req">*</span>
                    </label>
                    <input
                        id="t-title"
                        className="input"
                        value={form.data.title}
                        onChange={(e) => form.setData('title', e.target.value)}
                        placeholder={t('cabinet.it_task_form.name_placeholder')}
                        maxLength={120}
                    />
                    {err('title') && <p className="hint" style={{ color: 'var(--danger)' }}>{err('title')}</p>}
                </div>

                <div className="field">
                    <label className="label" htmlFor="t-type">
                        {t('cabinet.it_task_form.service')} <span className="req">*</span>
                    </label>
                    <select
                        id="t-type"
                        className="select"
                        value={form.data.service_type}
                        onChange={(e) => form.setData('service_type', e.target.value)}
                    >
                        {Object.entries(serviceTypes).map(([code, label]) => (
                            <option key={code} value={code}>
                                {label}
                            </option>
                        ))}
                    </select>
                </div>

                <div className="field">
                    <label className="label" htmlFor="t-desc">
                        {t('cabinet.it_task_form.description')} <span className="req">*</span>
                    </label>
                    <textarea
                        id="t-desc"
                        className="input"
                        rows={9}
                        value={form.data.description}
                        onChange={(e) => form.setData('description', e.target.value)}
                        placeholder={t('cabinet.it_task_form.description_placeholder')}
                    />
                    {err('description') && <p className="hint" style={{ color: 'var(--danger)' }}>{err('description')}</p>}
                </div>

                <div className="field">
                    <label className="label" htmlFor="t-stack">
                        {t('cabinet.it_task_form.stack')}
                    </label>
                    <div className="row wrap" style={{ gap: 6, marginBottom: form.data.stack.length ? 8 : 0 }}>
                        {form.data.stack.map((s) => (
                            <span key={s} className="chip chip-active row" style={{ gap: 4 }}>
                                {s}
                                <button
                                    type="button"
                                    aria-label={t('cabinet.it_task_form.remove_tag', { tag: s })}
                                    onClick={() => form.setData('stack', form.data.stack.filter((x) => x !== s))}
                                    style={{ display: 'inline-flex' }}
                                >
                                    <X aria-hidden className="size-3" />
                                </button>
                            </span>
                        ))}
                    </div>
                    <div className="row" style={{ gap: 8 }}>
                        <input
                            id="t-stack"
                            className="input"
                            value={tag}
                            onChange={(e) => setTag(e.target.value)}
                            onKeyDown={(e) => {
                                if (e.key === 'Enter' || e.key === ',') {
                                    e.preventDefault();
                                    addTag();
                                }
                            }}
                            placeholder={t('cabinet.it_task_form.stack_placeholder')}
                            maxLength={30}
                            disabled={form.data.stack.length >= 10}
                        />
                        <button type="button" className="btn btn-secondary" onClick={addTag} disabled={!tag.trim()}>
                            {t('cabinet.it_task_form.add')}
                        </button>
                    </div>
                    <p className="hint">{t('cabinet.it_task_form.stack_hint')}</p>
                </div>

                <div className="field">
                    <span className="label">{t('cabinet.it_task_form.budget')}</span>
                    <div className="row wrap" style={{ gap: 6 }}>
                        {(['negotiable', 'fixed', 'range'] as const).map((value) => (
                            <button
                                key={value}
                                type="button"
                                className={cn('chip', form.data.budget_type === value && 'chip-active')}
                                aria-pressed={form.data.budget_type === value}
                                onClick={() => form.setData('budget_type', value)}
                            >
                                {t(`cabinet.it_task_form.budget_${value}`)}
                            </button>
                        ))}
                    </div>
                    {form.data.budget_type !== 'negotiable' && (
                        <div className="row wrap mt-12" style={{ gap: 8, alignItems: 'flex-start' }}>
                            <div style={{ flex: 1, minWidth: 140 }}>
                                <input
                                    className="input"
                                    type="number"
                                    min={0}
                                    inputMode="numeric"
                                    aria-label={
                                        form.data.budget_type === 'range'
                                            ? t('cabinet.it_task_form.budget_from')
                                            : t('cabinet.it_task_form.budget')
                                    }
                                    placeholder={
                                        form.data.budget_type === 'range'
                                            ? t('cabinet.it_task_form.from')
                                            : t('cabinet.it_task_form.amount')
                                    }
                                    value={form.data.budget_from}
                                    onChange={(e) => form.setData('budget_from', e.target.value)}
                                />
                                {err('budget_from') && <p className="hint" style={{ color: 'var(--danger)' }}>{err('budget_from')}</p>}
                            </div>
                            {form.data.budget_type === 'range' && (
                                <div style={{ flex: 1, minWidth: 140 }}>
                                    <input
                                        className="input"
                                        type="number"
                                        min={0}
                                        inputMode="numeric"
                                        aria-label={t('cabinet.it_task_form.budget_to')}
                                        placeholder={t('cabinet.it_task_form.to')}
                                        value={form.data.budget_to}
                                        onChange={(e) => form.setData('budget_to', e.target.value)}
                                    />
                                    {err('budget_to') && <p className="hint" style={{ color: 'var(--danger)' }}>{err('budget_to')}</p>}
                                </div>
                            )}
                            <select
                                className="select"
                                style={{ width: 'auto' }}
                                aria-label={t('cabinet.it_task_form.currency')}
                                value={form.data.currency}
                                onChange={(e) => form.setData('currency', e.target.value)}
                            >
                                {currencies.map((c) => (
                                    <option key={c} value={c}>
                                        {c === 'UZS' ? t('catalog.currency_uzs') : c}
                                    </option>
                                ))}
                            </select>
                        </div>
                    )}
                </div>

                <div className="field">
                    <label className="label" htmlFor="t-deadline">
                        {t('cabinet.it_task_form.deadline')}
                    </label>
                    <input
                        id="t-deadline"
                        className="input"
                        type="date"
                        style={{ maxWidth: 220 }}
                        value={form.data.deadline_at}
                        onChange={(e) => form.setData('deadline_at', e.target.value)}
                    />
                    {err('deadline_at') && <p className="hint" style={{ color: 'var(--danger)' }}>{err('deadline_at')}</p>}
                </div>

                <div className="field">
                    <span className="label">{t('cabinet.it_task_form.files')}</span>
                    {files.length > 0 && (
                        <ul style={{ display: 'grid', gap: 6, marginBottom: 10, padding: 0, listStyle: 'none' }}>
                            {files.map((f) => (
                                <li key={f.id} className="row" style={{ gap: 8, justifyContent: 'space-between' }}>
                                    <span className="row t-sm" style={{ gap: 6 }}>
                                        <Paperclip aria-hidden className="size-4 muted" /> {f.title}{' '}
                                        <span className="muted">· {f.size}</span>
                                    </span>
                                    <button
                                        type="button"
                                        className="btn btn-ghost btn-sm"
                                        aria-label={t('cabinet.it_task_form.remove_file', { title: f.title })}
                                        onClick={() =>
                                            task &&
                                            confirm({
                                                title: t('cabinet.it_task_form.delete_file'),
                                                description: f.title,
                                                confirmLabel: t('common.delete'),
                                                danger: true,
                                                onConfirm: () =>
                                                    router.delete(routes.itTaskFileDelete(task.id, f.id), { preserveScroll: true }),
                                            })
                                        }
                                    >
                                        <Trash2 aria-hidden className="size-4" />
                                    </button>
                                </li>
                            ))}
                        </ul>
                    )}
                    {roomForFiles > 0 ? (
                        <>
                            <input
                                className="input"
                                type="file"
                                multiple
                                accept=".pdf,.doc,.docx,.xls,.xlsx,.ppt,.pptx,.txt,.jpg,.jpeg,.png,.zip"
                                onChange={(e) => form.setData('files', Array.from(e.target.files ?? []).slice(0, roomForFiles))}
                            />
                            <p className="hint">
                                {t('cabinet.it_task_form.files_hint', { count: roomForFiles })}
                            </p>
                        </>
                    ) : (
                        <p className="hint">{t('cabinet.it_task_form.files_full', { max: MAX_FILES })}</p>
                    )}
                    {(err('files') || err('files.0')) && (
                        <p className="hint" style={{ color: 'var(--danger)' }}>{err('files') ?? err('files.0')}</p>
                    )}
                </div>

                <div className="row" style={{ gap: 10, marginTop: 24 }}>
                    <button className="btn btn-primary" type="submit" disabled={form.processing}>
                        {task ? t('common.save') : t('cabinet.it_task_form.publish')}
                    </button>
                    {form.progress && (
                        <span className="t-sm muted">
                            {t('cabinet.it_task_form.progress', { percent: form.progress.percentage ?? 0 })}
                        </span>
                    )}
                </div>
                {!task && (
                    <p className="hint mt-12">{t('cabinet.it_task_form.after_publish')}</p>
                )}
            </form>
        </CabinetLayout>
    );
}
