import { Briefcase, GraduationCap, Languages, Lock, Mail, MapPin, Phone, Wallet } from 'lucide-react';
import { Link } from '@/components/ui/Link';
import { ResumeCard, experienceLabel, salaryLabel, type ResumeRow } from '@/components/ResumeCard';
import { PublicLayout } from '@/layouts/PublicLayout';
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

interface Resume extends ResumeRow {
    about: string | null;
    jobs: Job[];
    education: Education[];
    languages: Language[];
    schedule: string[];
    views: number;
    /** null — посетитель не вошёл: контакты живого человека не для анонимов */
    contacts: { name?: string; phone?: string; email?: string } | null;
}

interface Props {
    resume: Resume;
    options: {
        fields: Record<string, string>;
        employment: Record<string, string>;
        schedule: Record<string, string>;
        language_levels: Record<string, string>;
        education_levels: Record<string, string>;
    };
    similar: ResumeRow[];
}

/** «2019-04» → «04.2019»; пусто — «по настоящее время». */
function period(value: string): string {
    if (!value) return t('resume.until_now');

    const [year, month] = value.split('-');

    return month ? `${month}.${year}` : year;
}

export default function ResumeShow({ resume, options, similar }: Props) {
    const place = [resume.city, resume.country].filter(Boolean).join(', ');

    return (
        <PublicLayout title={resume.title} description={resume.about ?? t('resume.meta_description')}>
            <div className="container" style={{ paddingBlock: '32px 96px' }}>
                <div className="grid" style={{ gridTemplateColumns: 'minmax(0,2fr) minmax(260px,1fr)', gap: 24 }}>
                    <div className="min-w-0">
                        <div className="card">
                            <div className="row wrap" style={{ gap: 16, alignItems: 'center' }}>
                                <span
                                    aria-hidden
                                    style={{
                                        width: 84,
                                        height: 84,
                                        borderRadius: 14,
                                        display: 'grid',
                                        placeItems: 'center',
                                        color: '#fff',
                                        fontSize: 26,
                                        background: resume.photo
                                            ? `url(${resume.photo}) center/cover`
                                            : 'linear-gradient(120deg,var(--primary-700),var(--primary-500))',
                                    }}
                                >
                                    {resume.photo ? '' : resume.initials}
                                </span>

                                <div style={{ minWidth: 0 }}>
                                    <h1 className="t-h2">{resume.title}</h1>
                                    <p className="t-body muted">{resume.name}</p>
                                </div>
                            </div>

                            <dl className="t-sm mt-16" style={{ display: 'grid', gap: 8, margin: '16px 0 0' }}>
                                <div className="row" style={{ gap: 8 }}>
                                    <Briefcase aria-hidden className="size-4 muted" />
                                    <dd style={{ margin: 0 }}>{experienceLabel(resume.experience)}</dd>
                                </div>
                                <div className="row" style={{ gap: 8 }}>
                                    <Wallet aria-hidden className="size-4 muted" />
                                    <dd style={{ margin: 0, fontWeight: 600 }}>
                                        {salaryLabel(resume.salary, resume.currency)}
                                    </dd>
                                </div>
                                {place && (
                                    <div className="row" style={{ gap: 8 }}>
                                        <MapPin aria-hidden className="size-4 muted" />
                                        <dd style={{ margin: 0 }}>{place}</dd>
                                    </div>
                                )}
                            </dl>

                            <div className="row wrap mt-16" style={{ gap: 6 }}>
                                {resume.field && (
                                    <span className="badge badge-neutral">
                                        {options.fields[resume.field] ?? resume.field}
                                    </span>
                                )}
                                {resume.employment.map((value) => (
                                    <span key={value} className="badge badge-neutral">
                                        {options.employment[value] ?? value}
                                    </span>
                                ))}
                                {resume.schedule.map((value) => (
                                    <span key={value} className="badge badge-neutral">
                                        {options.schedule[value] ?? value}
                                    </span>
                                ))}
                            </div>
                        </div>

                        {resume.about && (
                            <section className="card mt-24">
                                <h2 className="t-h3" style={{ marginBottom: 12 }}>{t('resume.about')}</h2>
                                <p style={{ whiteSpace: 'pre-line' }}>{resume.about}</p>
                            </section>
                        )}

                        {resume.jobs.length > 0 && (
                            <section className="card mt-24">
                                <h2 className="t-h3" style={{ marginBottom: 16 }}>{t('resume.jobs')}</h2>
                                {resume.jobs.map((job, i) => (
                                    <div key={i} style={{ marginBottom: 20 }}>
                                        <p className="t-sm muted">
                                            {period(job.start)} — {period(job.end)}
                                        </p>
                                        <b>{job.position}</b>
                                        {job.company && <p className="t-sm">{job.company}</p>}
                                        {job.duties && (
                                            <p className="t-sm mt-8" style={{ whiteSpace: 'pre-line' }}>{job.duties}</p>
                                        )}
                                    </div>
                                ))}
                            </section>
                        )}

                        {resume.education.length > 0 && (
                            <section className="card mt-24">
                                <h2 className="t-h3" style={{ marginBottom: 16 }}>
                                    <GraduationCap aria-hidden className="size-5" /> {t('resume.education')}
                                </h2>
                                {resume.education.map((row, i) => (
                                    <div key={i} style={{ marginBottom: 16 }}>
                                        <b>{row.institution}</b>
                                        <p className="t-sm muted">
                                            {[
                                                row.faculty,
                                                row.level ? options.education_levels[row.level] : null,
                                                row.year,
                                            ]
                                                .filter(Boolean)
                                                .join(' · ')}
                                        </p>
                                    </div>
                                ))}
                            </section>
                        )}

                        {resume.languages.length > 0 && (
                            <section className="card mt-24">
                                <h2 className="t-h3" style={{ marginBottom: 16 }}>
                                    <Languages aria-hidden className="size-5" /> {t('resume.languages')}
                                </h2>
                                <div className="row wrap" style={{ gap: 8 }}>
                                    {resume.languages.map((row, i) => (
                                        <span key={i} className="badge badge-neutral">
                                            {row.name}
                                            {row.level ? ` — ${options.language_levels[row.level] ?? row.level}` : ''}
                                        </span>
                                    ))}
                                </div>
                            </section>
                        )}
                    </div>

                    <aside>
                        <div className="card">
                            <h2 className="t-h4" style={{ marginBottom: 12 }}>{t('resume.contacts')}</h2>

                            {resume.contacts === null ? (
                                <>
                                    <p className="t-sm muted" style={{ marginBottom: 12 }}>
                                        <Lock aria-hidden className="size-4" /> {t('resume.contacts_guest')}
                                    </p>
                                    <Link href={routes.login} className="btn btn-primary btn-block">
                                        {t('resume.login')}
                                    </Link>
                                </>
                            ) : (
                                <dl style={{ display: 'grid', gap: 10, margin: 0 }}>
                                    {resume.contacts.phone && (
                                        <div className="row" style={{ gap: 8 }}>
                                            <Phone aria-hidden className="size-4 muted" />
                                            <dd style={{ margin: 0 }}>
                                                <a href={`tel:${resume.contacts.phone.replace(/[^\d+]/g, '')}`}>
                                                    {resume.contacts.phone}
                                                </a>
                                            </dd>
                                        </div>
                                    )}
                                    {resume.contacts.email && (
                                        <div className="row" style={{ gap: 8 }}>
                                            <Mail aria-hidden className="size-4 muted" />
                                            <dd style={{ margin: 0 }}>
                                                <a href={`mailto:${resume.contacts.email}`}>{resume.contacts.email}</a>
                                            </dd>
                                        </div>
                                    )}
                                    {!resume.contacts.phone && !resume.contacts.email && (
                                        <p className="t-sm muted">{t('resume.contacts_hint')}</p>
                                    )}
                                </dl>
                            )}

                            {resume.skills.length > 0 && (
                                <>
                                    <h3 className="t-h4" style={{ margin: '20px 0 10px' }}>{t('resume.skills')}</h3>
                                    <div className="row wrap" style={{ gap: 6 }}>
                                        {resume.skills.map((skill) => (
                                            <span key={skill} className="badge badge-neutral">{skill}</span>
                                        ))}
                                    </div>
                                </>
                            )}

                            <p className="t-caption muted mt-16">
                                {t('resume.views', { count: String(resume.views) })}
                                {resume.published && ` · ${t('resume.published', { date: resume.published })}`}
                            </p>
                        </div>
                    </aside>
                </div>

                {similar.length > 0 && (
                    <section style={{ marginTop: 40 }}>
                        <h2 className="t-h3" style={{ marginBottom: 16 }}>{t('resume.similar')}</h2>
                        <div className="grid grid-3">
                            {similar.map((row) => (
                                <ResumeCard key={row.id} row={row} fields={options.fields} />
                            ))}
                        </div>
                    </section>
                )}
            </div>
        </PublicLayout>
    );
}
