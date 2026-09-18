import { router, useForm } from '@inertiajs/react';
import { Eye, Plus, Trash2, Upload, X } from 'lucide-react';
import { useRef } from 'react';
import { Panel } from '@/components/cabinet';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { cn } from '@/lib/cn';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';

interface Job {
    company: string;
    position: string;
    start: string;
    end: string;
    duties: string;
}

interface Education {
    institution: string;
    faculty: string;
    level: string;
    year: number | null;
}

interface Language {
    name: string;
    level: string;
}

interface ResumeData {
    id: number;
    slug: string;
    title: string;
    field: string | null;
    country_id: number | null;
    city_id: number | null;
    salary: number | null;
    currency: string;
    employment: string[];
    schedule: string[];
    about: string | null;
    skills: string[];
    jobs: Job[];
    education: Education[];
    languages: Language[];
    contact_name: string | null;
    contact_phone: string | null;
    contact_email: string | null;
    show_phone: boolean;
    show_email: boolean;
    photo: string | null;
    status: 'draft' | 'published' | 'hidden' | 'blocked';
    moderation_note: string | null;
    views: number;
    experience: { years: number; months: number };
}

interface Props {
    resume: ResumeData | null;
    defaults: { contact_name: string; contact_email: string; contact_phone: string | null };
    options: {
        fields: Record<string, string>;
        employment: Record<string, string>;
        schedule: Record<string, string>;
        language_levels: Record<string, string>;
        education_levels: Record<string, string>;
        currencies: Record<string, string>;
    };
    countries: { id: number; name: string }[];
    cities: { id: number; name: string; country_id: number }[];
}

/** Форма правится целиком, поэтому её состав описан явно: без этого
 *  TypeScript выводит тип по первому значению и считает, что страну
 *  нельзя очистить. */
interface Form {
    title: string;
    field: string;
    country_id: number | null;
    city_id: number | null;
    salary: number | null;
    currency: string;
    employment: string[];
    schedule: string[];
    about: string;
    skills: string[];
    jobs: Job[];
    education: Education[];
    languages: Language[];
    contact_name: string;
    contact_phone: string;
    contact_email: string;
    show_phone: boolean;
    show_email: boolean;
}

const EMPTY_JOB: Job = { company: '', position: '', start: '', end: '', duties: '' };
const EMPTY_EDUCATION: Education = { institution: '', faculty: '', level: '', year: null };
const EMPTY_LANGUAGE: Language = { name: '', level: '' };

/**
 * «Моё резюме» — одно на человека и бесплатное.
 *
 * Одна страница вместо мастера: резюме заполняют целиком и один раз,
 * а шаги заставляли бы проходить всё заново ради правки телефона.
 * Черновик сохраняется отдельно от публикации — человек может
 * дописывать его неделю, и никто этого не увидит.
 */
export default function Resume({ resume, defaults, options, countries, cities }: Props) {
    const photoInput = useRef<HTMLInputElement>(null);

    const form = useForm<Form>({
        title: resume?.title ?? '',
        field: resume?.field ?? '',
        country_id: resume?.country_id ?? countries[0]?.id ?? null,
        city_id: resume?.city_id ?? null,
        salary: resume?.salary ?? null,
        currency: resume?.currency ?? 'UZS',
        employment: resume?.employment ?? ['full'],
        schedule: resume?.schedule ?? ['full_day'],
        about: resume?.about ?? '',
        skills: resume?.skills ?? [],
        jobs: resume?.jobs ?? [],
        education: resume?.education ?? [],
        languages: resume?.languages ?? [],
        contact_name: resume?.contact_name ?? defaults.contact_name,
        contact_phone: resume?.contact_phone ?? defaults.contact_phone ?? '',
        contact_email: resume?.contact_email ?? defaults.contact_email,
        show_phone: resume?.show_phone ?? true,
        show_email: resume?.show_email ?? true,
    });

    function toggle(key: 'employment' | 'schedule', value: string) {
        const current = form.data[key];

        form.setData(
            key,
            current.includes(value) ? current.filter((v) => v !== value) : [...current, value],
        );
    }

    /* Списки правятся по месту: копия массива, а не мутация —
       иначе React не увидит изменения и поле не перерисуется */
    function patch<T>(key: 'jobs' | 'education' | 'languages', index: number, changes: Partial<T>) {
        const next = [...(form.data[key] as T[])];
        next[index] = { ...next[index], ...changes };
        form.setData(key, next as never);
    }

    function remove(key: 'jobs' | 'education' | 'languages', index: number) {
        form.setData(key, (form.data[key] as unknown[]).filter((_, i) => i !== index) as never);
    }

    const availableCities = form.data.country_id === null
        ? cities
        : cities.filter((c) => c.country_id === form.data.country_id);

    const status = resume?.status ?? 'draft';

    return (
        <CabinetLayout
            title={t('resume.my_title')}
            heading={t('resume.my_title')}
            subheading={t('resume.my_lead')}
            actions={
                <div className="row wrap" style={{ gap: 8 }}>
                    <span
                        className={cn(
                            'badge',
                            status === 'published' ? 'badge-supply' : status === 'blocked' ? 'badge-warning' : 'badge-neutral',
                        )}
                    >
                        {t(`resume.status_${status}`)}
                    </span>

                    {resume && status === 'published' && (
                        <a href={routes.resume(resume.slug)} className="btn btn-ghost btn-sm" target="_blank" rel="noreferrer">
                            <Eye aria-hidden className="size-4" /> {t('resume.open')}
                        </a>
                    )}
                </div>
            }
        >

            {resume?.moderation_note && (
                <div className="card mb-16" style={{ borderColor: 'rgba(220,38,38,.3)' }}>
                    <p className="t-sm">{resume.moderation_note}</p>
                </div>
            )}

            <Panel title={t('resume.position')}>
                {resume && (
                    <div className="row wrap" style={{ gap: 16, marginBottom: 20, alignItems: 'center' }}>
                        <div
                            className="avatar-lg"
                            style={{
                                width: 96,
                                height: 96,
                                borderRadius: 12,
                                background: resume.photo
                                    ? `url(${resume.photo}) center/cover`
                                    : 'linear-gradient(120deg,var(--primary-700),var(--primary-500))',
                            }}
                        />
                        <div>
                            <button
                                type="button"
                                className="btn btn-secondary btn-sm"
                                onClick={() => photoInput.current?.click()}
                            >
                                <Upload aria-hidden className="size-4" /> {t('resume.photo')}
                            </button>
                            <p className="hint">{t('resume.photo_hint')}</p>
                        </div>
                        <input
                            ref={photoInput}
                            type="file"
                            accept="image/jpeg,image/png,image/webp"
                            hidden
                            onChange={(e) => {
                                const file = e.target.files?.[0];
                                if (!file) return;
                                router.post('/cabinet/resume/photo', { photo: file }, { preserveScroll: true, forceFormData: true });
                                e.target.value = '';
                            }}
                        />
                    </div>
                )}

                <div className="field">
                    <label className="label" htmlFor="r-title">
                        {t('resume.position')} <span className="req">*</span>
                    </label>
                    <input
                        id="r-title"
                        className="input"
                        value={form.data.title}
                        placeholder={t('resume.position_hint')}
                        onChange={(e) => form.setData('title', e.target.value)}
                    />
                    {form.errors.title && <p className="hint" style={{ color: 'var(--danger)' }}>{form.errors.title}</p>}
                </div>

                <div className="grid grid-2" style={{ gap: 16 }}>
                    <div className="field">
                        <label className="label" htmlFor="r-field">{t('resume.field')}</label>
                        <select
                            id="r-field"
                            className="input"
                            value={form.data.field}
                            onChange={(e) => form.setData('field', e.target.value)}
                        >
                            <option value="">{t('resume.field_any')}</option>
                            {Object.entries(options.fields).map(([value, label]) => (
                                <option key={value} value={value}>{label}</option>
                            ))}
                        </select>
                    </div>

                    <div className="field">
                        <label className="label" htmlFor="r-salary">{t('resume.salary_label')}</label>
                        <div className="row" style={{ gap: 8 }}>
                            <input
                                id="r-salary"
                                className="input"
                                type="number"
                                min={0}
                                value={form.data.salary ?? ''}
                                onChange={(e) => form.setData('salary', e.target.value === '' ? null : Number(e.target.value))}
                            />
                            <select
                                className="input"
                                style={{ maxWidth: 120 }}
                                aria-label={t('resume.salary_label')}
                                value={form.data.currency}
                                onChange={(e) => form.setData('currency', e.target.value)}
                            >
                                {Object.keys(options.currencies).map((code) => (
                                    <option key={code} value={code}>{code}</option>
                                ))}
                            </select>
                        </div>
                    </div>
                </div>

                <div className="grid grid-2" style={{ gap: 16 }}>
                    <div className="field">
                        <label className="label" htmlFor="r-country">{t('resume.location')}</label>
                        <select
                            id="r-country"
                            className="input"
                            value={form.data.country_id ?? ''}
                            onChange={(e) => {
                                form.setData('country_id', e.target.value === '' ? null : Number(e.target.value));
                                form.setData('city_id', null);
                            }}
                        >
                            <option value="">{t('resume.field_any')}</option>
                            {countries.map((c) => (
                                <option key={c.id} value={c.id}>{c.name}</option>
                            ))}
                        </select>
                    </div>

                    <div className="field">
                        <label className="label" htmlFor="r-city">{t('resume.city')}</label>
                        <select
                            id="r-city"
                            className="input"
                            value={form.data.city_id ?? ''}
                            onChange={(e) => form.setData('city_id', e.target.value === '' ? null : Number(e.target.value))}
                        >
                            <option value="">{t('resume.city_any')}</option>
                            {availableCities.map((c) => (
                                <option key={c.id} value={c.id}>{c.name}</option>
                            ))}
                        </select>
                    </div>
                </div>

                <div className="field">
                    <span className="label">{t('resume.employment')}</span>
                    <div className="row wrap" style={{ gap: 6 }}>
                        {Object.entries(options.employment).map(([value, label]) => (
                            <button
                                key={value}
                                type="button"
                                className={cn('chip', form.data.employment.includes(value) && 'chip-active')}
                                aria-pressed={form.data.employment.includes(value)}
                                onClick={() => toggle('employment', value)}
                            >
                                {label}
                            </button>
                        ))}
                    </div>
                </div>

                <div className="field">
                    <span className="label">{t('resume.schedule')}</span>
                    <div className="row wrap" style={{ gap: 6 }}>
                        {Object.entries(options.schedule).map(([value, label]) => (
                            <button
                                key={value}
                                type="button"
                                className={cn('chip', form.data.schedule.includes(value) && 'chip-active')}
                                aria-pressed={form.data.schedule.includes(value)}
                                onClick={() => toggle('schedule', value)}
                            >
                                {label}
                            </button>
                        ))}
                    </div>
                </div>
            </Panel>

            <Panel title={t('resume.about')}>
                <div className="field">
                    <label className="sr-only" htmlFor="r-about">{t('resume.about')}</label>
                    <textarea
                        id="r-about"
                        className="input"
                        rows={6}
                        value={form.data.about}
                        placeholder={t('resume.about_hint')}
                        onChange={(e) => form.setData('about', e.target.value)}
                    />
                </div>

                <div className="field">
                    <label className="label" htmlFor="r-skills">{t('resume.skills')}</label>
                    {/* Навыки — по строке на каждый: теги с крестиками
                        выглядят красивее, но ломаются на телефоне */}
                    <textarea
                        id="r-skills"
                        className="input"
                        rows={4}
                        value={form.data.skills.join('\n')}
                        onChange={(e) => form.setData('skills', e.target.value.split('\n'))}
                    />
                    <p className="hint">{t('resume.skills_hint')}</p>
                </div>
            </Panel>

            <Panel title={t('resume.jobs')}>
                {form.data.jobs.map((job, i) => (
                    <div key={i} className="card mb-16">
                        <div className="row-between" style={{ marginBottom: 12 }}>
                            <b className="t-sm muted">{i + 1}</b>
                            <button type="button" className="btn btn-ghost btn-sm" onClick={() => remove('jobs', i)}>
                                <X aria-hidden className="size-4" /> {t('resume.remove')}
                            </button>
                        </div>

                        <div className="grid grid-2" style={{ gap: 16 }}>
                            <div className="field">
                                <label className="label">{t('resume.job_company')}</label>
                                <input
                                    className="input"
                                    value={job.company}
                                    onChange={(e) => patch<Job>('jobs', i, { company: e.target.value })}
                                />
                            </div>
                            <div className="field">
                                <label className="label">{t('resume.job_position')}</label>
                                <input
                                    className="input"
                                    value={job.position}
                                    onChange={(e) => patch<Job>('jobs', i, { position: e.target.value })}
                                />
                            </div>
                            <div className="field">
                                <label className="label">{t('resume.job_start')}</label>
                                <input
                                    className="input"
                                    type="month"
                                    value={job.start}
                                    onChange={(e) => patch<Job>('jobs', i, { start: e.target.value })}
                                />
                            </div>
                            <div className="field">
                                <label className="label">{t('resume.job_end')}</label>
                                <input
                                    className="input"
                                    type="month"
                                    value={job.end}
                                    onChange={(e) => patch<Job>('jobs', i, { end: e.target.value })}
                                />
                                <p className="hint">{t('resume.job_end_hint')}</p>
                            </div>
                        </div>

                        <div className="field">
                            <label className="label">{t('resume.job_duties')}</label>
                            <textarea
                                className="input"
                                rows={3}
                                value={job.duties}
                                onChange={(e) => patch<Job>('jobs', i, { duties: e.target.value })}
                            />
                        </div>
                    </div>
                ))}

                <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => form.setData('jobs', [...form.data.jobs, { ...EMPTY_JOB }])}
                >
                    <Plus aria-hidden className="size-4" /> {t('resume.add_job')}
                </button>
            </Panel>

            <Panel title={t('resume.education')}>
                {form.data.education.map((row, i) => (
                    <div key={i} className="card mb-16">
                        <div className="row-between" style={{ marginBottom: 12 }}>
                            <b className="t-sm muted">{i + 1}</b>
                            <button type="button" className="btn btn-ghost btn-sm" onClick={() => remove('education', i)}>
                                <X aria-hidden className="size-4" /> {t('resume.remove')}
                            </button>
                        </div>

                        <div className="grid grid-2" style={{ gap: 16 }}>
                            <div className="field">
                                <label className="label">{t('resume.edu_institution')}</label>
                                <input
                                    className="input"
                                    value={row.institution}
                                    onChange={(e) => patch<Education>('education', i, { institution: e.target.value })}
                                />
                            </div>
                            <div className="field">
                                <label className="label">{t('resume.edu_faculty')}</label>
                                <input
                                    className="input"
                                    value={row.faculty}
                                    onChange={(e) => patch<Education>('education', i, { faculty: e.target.value })}
                                />
                            </div>
                            <div className="field">
                                <label className="label">{t('resume.edu_level')}</label>
                                <select
                                    className="input"
                                    value={row.level}
                                    onChange={(e) => patch<Education>('education', i, { level: e.target.value })}
                                >
                                    <option value="" />
                                    {Object.entries(options.education_levels).map(([value, label]) => (
                                        <option key={value} value={value}>{label}</option>
                                    ))}
                                </select>
                            </div>
                            <div className="field">
                                <label className="label">{t('resume.edu_year')}</label>
                                <input
                                    className="input"
                                    type="number"
                                    value={row.year ?? ''}
                                    onChange={(e) =>
                                        patch<Education>('education', i, {
                                            year: e.target.value === '' ? null : Number(e.target.value),
                                        })
                                    }
                                />
                            </div>
                        </div>
                    </div>
                ))}

                <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => form.setData('education', [...form.data.education, { ...EMPTY_EDUCATION }])}
                >
                    <Plus aria-hidden className="size-4" /> {t('resume.add_education')}
                </button>
            </Panel>

            <Panel title={t('resume.languages')}>
                {form.data.languages.map((row, i) => (
                    <div key={i} className="row wrap mb-16" style={{ gap: 12, alignItems: 'flex-end' }}>
                        <div className="field" style={{ flex: 1, minWidth: 160, marginBottom: 0 }}>
                            <label className="label">{t('resume.language_name')}</label>
                            <input
                                className="input"
                                value={row.name}
                                onChange={(e) => patch<Language>('languages', i, { name: e.target.value })}
                            />
                        </div>
                        <div className="field" style={{ flex: 1, minWidth: 160, marginBottom: 0 }}>
                            <label className="label">{t('resume.language_level')}</label>
                            <select
                                className="input"
                                value={row.level}
                                onChange={(e) => patch<Language>('languages', i, { level: e.target.value })}
                            >
                                <option value="" />
                                {Object.entries(options.language_levels).map(([value, label]) => (
                                    <option key={value} value={value}>{label}</option>
                                ))}
                            </select>
                        </div>
                        <button type="button" className="btn btn-ghost btn-sm" onClick={() => remove('languages', i)}>
                            <X aria-hidden className="size-4" /> {t('resume.remove')}
                        </button>
                    </div>
                ))}

                <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => form.setData('languages', [...form.data.languages, { ...EMPTY_LANGUAGE }])}
                >
                    <Plus aria-hidden className="size-4" /> {t('resume.add_language')}
                </button>
            </Panel>

            <Panel title={t('resume.contacts')}>
                <div className="grid grid-2" style={{ gap: 16 }}>
                    <div className="field">
                        <label className="label" htmlFor="r-name">{t('resume.contact_name')}</label>
                        <input
                            id="r-name"
                            className="input"
                            value={form.data.contact_name}
                            onChange={(e) => form.setData('contact_name', e.target.value)}
                        />
                    </div>
                    <div className="field">
                        <label className="label" htmlFor="r-phone">{t('resume.contact_phone')}</label>
                        <input
                            id="r-phone"
                            className="input"
                            value={form.data.contact_phone}
                            onChange={(e) => form.setData('contact_phone', e.target.value)}
                        />
                    </div>
                    <div className="field">
                        <label className="label" htmlFor="r-email">{t('resume.contact_email')}</label>
                        <input
                            id="r-email"
                            className="input"
                            type="email"
                            value={form.data.contact_email}
                            onChange={(e) => form.setData('contact_email', e.target.value)}
                        />
                        {form.errors.contact_email && (
                            <p className="hint" style={{ color: 'var(--danger)' }}>{form.errors.contact_email}</p>
                        )}
                    </div>
                </div>

                <label className="check">
                    <input
                        type="checkbox"
                        checked={form.data.show_phone}
                        onChange={(e) => form.setData('show_phone', e.target.checked)}
                    />
                    {t('resume.show_phone')}
                </label>
                <label className="check mt-12">
                    <input
                        type="checkbox"
                        checked={form.data.show_email}
                        onChange={(e) => form.setData('show_email', e.target.checked)}
                    />
                    {t('resume.show_email')}
                </label>
                <p className="hint mt-8">{t('resume.contacts_hint')}</p>
            </Panel>

            <div className="row wrap" style={{ gap: 8, marginTop: 24 }}>
                <button
                    type="button"
                    className="btn btn-primary"
                    disabled={form.processing}
                    onClick={() => form.patch('/cabinet/resume', { preserveScroll: true })}
                >
                    {resume ? t('resume.save') : t('resume.create')}
                </button>

                {resume && status !== 'published' && status !== 'blocked' && (
                    <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => router.post('/cabinet/resume/publish', {}, { preserveScroll: true })}
                    >
                        {t('resume.publish')}
                    </button>
                )}

                {resume && status === 'published' && (
                    <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={() => router.post('/cabinet/resume/hide', {}, { preserveScroll: true })}
                    >
                        {t('resume.hide')}
                    </button>
                )}

                {resume && (
                    <button
                        type="button"
                        className="btn btn-ghost"
                        onClick={() => router.delete('/cabinet/resume', { preserveScroll: true })}
                    >
                        <Trash2 aria-hidden className="size-4" /> {t('resume.delete')}
                    </button>
                )}
            </div>
        </CabinetLayout>
    );
}
