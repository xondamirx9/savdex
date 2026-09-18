import { router } from '@inertiajs/react';
import { Users } from 'lucide-react';
import { useState } from 'react';
import { Link } from '@/components/ui/Link';
import { ResumeCard, type ResumeRow } from '@/components/ResumeCard';
import { SelectField } from '@/components/SelectField';
import { PublicLayout } from '@/layouts/PublicLayout';
import { cn } from '@/lib/cn';
import { t, tChoice } from '@/lib/i18n';
import { routes } from '@/routes';

interface Props {
    resumes: {
        data: ResumeRow[];
        links: { url: string | null; label: string; active: boolean }[];
        current_page: number;
        last_page: number;
    };
    filters: {
        q: string;
        field: string | null;
        city: number | null;
        experience: string | null;
        employment: string | null;
    };
    options: {
        fields: Record<string, string>;
        experience: Record<string, string>;
        employment: Record<string, string>;
    };
    cities: { id: number; name: string }[];
    total: number;
}

/**
 * Раздел «Резюме»: кого можно нанять.
 *
 * Бесплатный с обеих сторон — ни соискатель не платит за публикацию,
 * ни компания за просмотр. Контакты открыты вошедшим: отдавать
 * телефон живого человека анониму площадка не будет.
 */
export default function ResumesIndex({ resumes, filters, options, cities, total }: Props) {
    const [q, setQ] = useState(filters.q);

    function apply(next: Partial<Props['filters']>) {
        router.get(
            routes.resumes,
            Object.fromEntries(
                // Пустые значения выкидываем: адрес с «?field=&city=»
                // невозможно ни прочитать, ни переслать коллеге
                Object.entries({ ...filters, ...next }).filter(([, v]) => v !== '' && v !== null),
            ),
            { preserveState: true, preserveScroll: true, replace: true },
        );
    }

    const hasFilters =
        filters.field !== null || filters.city !== null || filters.experience !== null || filters.employment !== null;

    return (
        <PublicLayout title={t('resume.meta_title')} description={t('resume.meta_description')}>
            <div className="container board-page">
                <div className="section-head-left" style={{ marginBottom: 20 }}>
                    <span className="eyebrow">{t('resume.eyebrow')}</span>
                    <h1 className="t-h1">{t('resume.h1')}</h1>
                    <p className="t-body muted">{t('resume.lead')}</p>
                </div>

                <div className="toolbar">
                    <div className="board-search">
                        <label htmlFor="resume-q" className="sr-only">{t('resume.search_label')}</label>
                        <input
                            id="resume-q"
                            className="input"
                            type="search"
                            placeholder={t('resume.search_placeholder')}
                            value={q}
                            onChange={(e) => setQ(e.target.value)}
                            onKeyDown={(e) => e.key === 'Enter' && apply({ q })}
                        />
                    </div>
                </div>

                <div className="row wrap" style={{ gap: 8, margin: '16px 0' }}>
                    <SelectField
                        className="select-field--auto"
                        ariaLabel={t('resume.field')}
                        placeholder={t('resume.field_any')}
                        value={filters.field ?? ''}
                        onChange={(v) => apply({ field: v === '' ? null : v })}
                        options={Object.entries(options.fields).map(([value, label]) => ({ value, label }))}
                    />

                    <SelectField
                        className="select-field--auto"
                        ariaLabel={t('resume.experience_filter')}
                        placeholder={t('resume.experience_any')}
                        value={filters.experience ?? ''}
                        onChange={(v) => apply({ experience: v === '' ? null : v })}
                        options={Object.entries(options.experience).map(([value, label]) => ({ value, label }))}
                    />

                    <SelectField
                        className="select-field--auto"
                        ariaLabel={t('resume.employment_filter')}
                        placeholder={t('resume.employment_any')}
                        value={filters.employment ?? ''}
                        onChange={(v) => apply({ employment: v === '' ? null : v })}
                        options={Object.entries(options.employment).map(([value, label]) => ({ value, label }))}
                    />

                    {cities.length > 0 && (
                        <SelectField
                            className="select-field--auto"
                            ariaLabel={t('resume.city')}
                            placeholder={t('resume.city_any')}
                            value={filters.city === null ? '' : String(filters.city)}
                            onChange={(v) => apply({ city: v === '' ? null : Number(v) })}
                            options={cities.map((c) => ({ value: String(c.id), label: c.name }))}
                        />
                    )}

                    {hasFilters && (
                        <button
                            type="button"
                            className="chip"
                            onClick={() => router.get(routes.resumes, filters.q ? { q: filters.q } : {})}
                        >
                            {t('resume.reset')}
                        </button>
                    )}

                    <span className="t-sm muted board-count">{tChoice('resume.found', total)}</span>
                </div>

                {resumes.data.length === 0 ? (
                    <div className="card empty">
                        <div className="empty-icon">
                            <Users aria-hidden className="size-7" />
                        </div>
                        <p className="t-h4">{t('resume.empty_title')}</p>
                        <p className="t-sm muted mt-8" style={{ maxWidth: 420, margin: '8px auto 0' }}>
                            {t('resume.empty_text')}
                        </p>
                    </div>
                ) : (
                    <div className="grid grid-3" data-reveal-stagger>
                        {resumes.data.map((row) => (
                            <ResumeCard key={row.id} row={row} fields={options.fields} />
                        ))}
                    </div>
                )}

                {resumes.last_page > 1 && (
                    <nav className="pagination mt-32" aria-label={t('resume.pages')}>
                        {resumes.links.map((link, i) =>
                            link.url ? (
                                <Link
                                    key={i}
                                    href={link.url}
                                    className={cn('page-link', link.active && 'is-active')}
                                    aria-current={link.active ? 'page' : undefined}
                                    dangerouslySetInnerHTML={{ __html: link.label }}
                                />
                            ) : (
                                <span
                                    key={i}
                                    className="page-link is-disabled"
                                    aria-disabled="true"
                                    dangerouslySetInnerHTML={{ __html: link.label }}
                                />
                            ),
                        )}
                    </nav>
                )}
            </div>
        </PublicLayout>
    );
}
