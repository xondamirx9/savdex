import { Briefcase, MapPin, Wallet } from 'lucide-react';
import { Link } from '@/components/ui/Link';
import { formatNumber } from '@/components/cabinet';
import { t, tChoice } from '@/lib/i18n';
import { routes } from '@/routes';

export interface ResumeRow {
    id: number;
    slug: string;
    title: string;
    field: string | null;
    name: string | null;
    initials: string;
    photo: string | null;
    city: string | null;
    country: string | null;
    salary: number | null;
    currency: string;
    employment: string[];
    experience: { years: number; months: number };
    skills: string[];
    published: string | null;
}

/** «5 лет 2 месяца» или «без опыта» — на языке страницы. */
export function experienceLabel(experience: { years: number; months: number }): string {
    if (experience.years === 0 && experience.months === 0) {
        return t('resume.no_experience');
    }

    const parts = [
        experience.years > 0 ? tChoice('resume.years', experience.years) : null,
        experience.months > 0 ? tChoice('resume.months', experience.months) : null,
    ].filter(Boolean);

    return t('resume.experience_value', { years: parts.join(' ') });
}

export function salaryLabel(salary: number | null, currency: string): string {
    if (salary === null) return t('resume.salary_any');

    const amount = `${formatNumber(salary)} ${currency === 'UZS' ? t('catalog.currency_uzs') : currency}`;

    return t('resume.salary_from', { amount });
}

/** Карточка соискателя — одна на выдачу раздела и блок похожих. */
export function ResumeCard({ row, fields }: { row: ResumeRow; fields: Record<string, string> }) {
    const place = [row.city, row.country].filter(Boolean).join(', ');

    return (
        <Link
            href={routes.resume(row.slug)}
            className="card lift"
            style={{ display: 'flex', flexDirection: 'column', gap: 12, color: 'inherit' }}
        >
            <div className="row" style={{ gap: 12, alignItems: 'center' }}>
                <span
                    aria-hidden
                    className="t-num"
                    style={{
                        width: 48,
                        height: 48,
                        flexShrink: 0,
                        borderRadius: 10,
                        display: 'grid',
                        placeItems: 'center',
                        color: '#fff',
                        background: row.photo
                            ? `url(${row.photo}) center/cover`
                            : 'linear-gradient(120deg,var(--primary-700),var(--primary-500))',
                    }}
                >
                    {row.photo ? '' : row.initials}
                </span>
                <span style={{ minWidth: 0 }}>
                    <b style={{ display: 'block' }}>{row.title}</b>
                    <span className="t-sm muted">{row.name}</span>
                </span>
            </div>

            <dl className="t-sm" style={{ display: 'grid', gap: 6, margin: 0, flex: 1 }}>
                <div className="row" style={{ gap: 8 }}>
                    <Briefcase aria-hidden className="size-4 muted" />
                    <dt className="sr-only">{t('resume.experience_filter')}</dt>
                    <dd style={{ margin: 0 }}>{experienceLabel(row.experience)}</dd>
                </div>
                <div className="row" style={{ gap: 8 }}>
                    <Wallet aria-hidden className="size-4 muted" />
                    <dt className="sr-only">{t('resume.salary_label')}</dt>
                    <dd style={{ margin: 0, fontWeight: 600 }}>{salaryLabel(row.salary, row.currency)}</dd>
                </div>
                {place && (
                    <div className="row" style={{ gap: 8 }}>
                        <MapPin aria-hidden className="size-4 muted" />
                        <dt className="sr-only">{t('resume.city')}</dt>
                        <dd style={{ margin: 0 }}>{place}</dd>
                    </div>
                )}
            </dl>

            <div className="row wrap" style={{ gap: 6 }}>
                {row.field && <span className="badge badge-neutral">{fields[row.field] ?? row.field}</span>}
                {row.skills.slice(0, 3).map((skill) => (
                    <span key={skill} className="badge badge-neutral">{skill}</span>
                ))}
            </div>
        </Link>
    );
}
