import { router, useForm } from '@inertiajs/react';
import { Link } from '@/components/ui/Link';
import { ArrowLeft, Paperclip, Trash2, X } from 'lucide-react';
import { useState } from 'react';
import { useConfirm } from '@/components/useConfirm';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { cn } from '@/lib/cn';
import { routes } from '@/routes';

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
            title={task ? 'Изменить IT-задачу' : 'Новая IT-задача'}
            heading={task ? 'Изменить IT-задачу' : 'Новая IT-задача'}
            subheading="Чем точнее описание, тем меньше вопросов у исполнителей и точнее их оценки"
            actions={
                <Link href={routes.cabinetItTasks} className="btn btn-secondary btn-sm">
                    <ArrowLeft aria-hidden className="size-4" /> Все задачи
                </Link>
            }
        >
            {dialog}

            <form onSubmit={submit} className="card" style={{ maxWidth: 760 }}>
                <div className="field">
                    <label className="label" htmlFor="t-title">
                        Название задачи <span className="req">*</span>
                    </label>
                    <input
                        id="t-title"
                        className="input"
                        value={form.data.title}
                        onChange={(e) => form.setData('title', e.target.value)}
                        placeholder="Интернет-магазин стройматериалов с оплатой картой"
                        maxLength={120}
                    />
                    {err('title') && <p className="hint" style={{ color: 'var(--danger)' }}>{err('title')}</p>}
                </div>

                <div className="field">
                    <label className="label" htmlFor="t-type">
                        Вид услуги <span className="req">*</span>
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
                        Описание <span className="req">*</span>
                    </label>
                    <textarea
                        id="t-desc"
                        className="input"
                        rows={9}
                        value={form.data.description}
                        onChange={(e) => form.setData('description', e.target.value)}
                        placeholder={
                            'Что нужно сделать и зачем. Что уже есть (сайт, 1С, база). Что должно получиться в итоге. Как будете принимать работу.'
                        }
                    />
                    {err('description') && <p className="hint" style={{ color: 'var(--danger)' }}>{err('description')}</p>}
                </div>

                <div className="field">
                    <label className="label" htmlFor="t-stack">
                        Технологии и стек
                    </label>
                    <div className="row wrap" style={{ gap: 6, marginBottom: form.data.stack.length ? 8 : 0 }}>
                        {form.data.stack.map((s) => (
                            <span key={s} className="chip chip-active row" style={{ gap: 4 }}>
                                {s}
                                <button
                                    type="button"
                                    aria-label={`Убрать ${s}`}
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
                            placeholder="Laravel, React, 1С, Telegram Bot API… Enter — добавить"
                            maxLength={30}
                            disabled={form.data.stack.length >= 10}
                        />
                        <button type="button" className="btn btn-secondary" onClick={addTag} disabled={!tag.trim()}>
                            Добавить
                        </button>
                    </div>
                    <p className="hint">Необязательно. До 10 технологий — по ним исполнители найдут вашу задачу.</p>
                </div>

                <div className="field">
                    <span className="label">Бюджет</span>
                    <div className="row wrap" style={{ gap: 6 }}>
                        {(
                            [
                                ['negotiable', 'Договорной'],
                                ['fixed', 'Фиксированный'],
                                ['range', 'Диапазон'],
                            ] as const
                        ).map(([value, label]) => (
                            <button
                                key={value}
                                type="button"
                                className={cn('chip', form.data.budget_type === value && 'chip-active')}
                                aria-pressed={form.data.budget_type === value}
                                onClick={() => form.setData('budget_type', value)}
                            >
                                {label}
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
                                    aria-label={form.data.budget_type === 'range' ? 'Бюджет от' : 'Бюджет'}
                                    placeholder={form.data.budget_type === 'range' ? 'от' : 'сумма'}
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
                                        aria-label="Бюджет до"
                                        placeholder="до"
                                        value={form.data.budget_to}
                                        onChange={(e) => form.setData('budget_to', e.target.value)}
                                    />
                                    {err('budget_to') && <p className="hint" style={{ color: 'var(--danger)' }}>{err('budget_to')}</p>}
                                </div>
                            )}
                            <select
                                className="select"
                                style={{ width: 'auto' }}
                                aria-label="Валюта"
                                value={form.data.currency}
                                onChange={(e) => form.setData('currency', e.target.value)}
                            >
                                {currencies.map((c) => (
                                    <option key={c} value={c}>
                                        {c === 'UZS' ? 'сум' : c}
                                    </option>
                                ))}
                            </select>
                        </div>
                    )}
                </div>

                <div className="field">
                    <label className="label" htmlFor="t-deadline">
                        Желаемый срок сдачи
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
                    <span className="label">Техзадание и файлы</span>
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
                                        aria-label={`Удалить ${f.title}`}
                                        onClick={() =>
                                            task &&
                                            confirm({
                                                title: 'Удалить файл?',
                                                description: f.title,
                                                confirmLabel: 'Удалить',
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
                                До {roomForFiles} файлов по 20 МБ: PDF, Word, Excel, презентации, изображения, ZIP. Файлы видны
                                только вошедшим пользователям.
                            </p>
                        </>
                    ) : (
                        <p className="hint">Достигнут максимум — {MAX_FILES} файлов. Удалите лишний, чтобы добавить новый.</p>
                    )}
                    {(err('files') || err('files.0')) && (
                        <p className="hint" style={{ color: 'var(--danger)' }}>{err('files') ?? err('files.0')}</p>
                    )}
                </div>

                <div className="row" style={{ gap: 10, marginTop: 24 }}>
                    <button className="btn btn-primary" type="submit" disabled={form.processing}>
                        {task ? 'Сохранить' : 'Опубликовать задачу'}
                    </button>
                    {form.progress && <span className="t-sm muted">Загрузка {form.progress.percentage}%</span>}
                </div>
                {!task && (
                    <p className="hint mt-12">
                        Задача появится в разделе «IT-услуги» сразу после публикации. Отклики исполнителей придут в «Чаты».
                    </p>
                )}
            </form>
        </CabinetLayout>
    );
}
