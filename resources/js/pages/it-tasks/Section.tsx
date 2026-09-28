import { ArrowRight, BriefcaseBusiness, CheckCircle2, FileUser, PlusCircle, Star, Users } from 'lucide-react';
import { CountUp } from '@/components/CountUp';
import { ResumeCard, type ResumeRow } from '@/components/ResumeCard';
import { VerificationBadge } from '@/components/VerificationBadge';
import { Link } from '@/components/ui/Link';
import { PublicLayout } from '@/layouts/PublicLayout';
import { cn } from '@/lib/cn';
import { t, tChoice } from '@/lib/i18n';
import { SERVICE_PAGE_ICONS } from '@/lib/serviceSections';
import { routes } from '@/routes';
import { TaskCard, type TaskRow } from './Index';

interface ProviderRow {
    slug: string;
    name: string;
    city: string | null;
    verification_level: number;
    rating: number;
    initials: string;
    logo: string | null;
    /** Виды этого направления, отмеченные в профиле исполнителя */
    specializations: string[];
}

interface Props {
    section: { slug: string; code: string; title: string; lead: string; offers: string[] };
    stats: { active: number; completed: number; providers: number; resumes: number | null };
    /** Что входит в направление: виды IT, у HR — подбор персонала и резюме */
    kinds: { label: string; href: string; count: number; kind: 'tasks' | 'resumes' }[];
    tasks: TaskRow[];
    completed: TaskRow[];
    providers: ProviderRow[];
    resumes: ResumeRow[];
    resumeFields: Record<string, string>;
    pages: { slug: string; title: string }[];
}

/**
 * Страница одного направления «Доп. услуг».
 *
 * Всё о направлении на одной странице: что можно заказать, сколько
 * задач и исполнителей, открытые и выполненные задачи, исполнители,
 * у HR-направлений — резюме. Полная лента с фильтрами — по ссылке
 * «Все задачи направления».
 */
export default function Section({
    section,
    stats,
    kinds,
    tasks,
    completed,
    providers,
    resumes,
    resumeFields,
    pages,
}: Props) {
    const Icon = SERVICE_PAGE_ICONS[section.slug] ?? BriefcaseBusiness;
    const feed = `${routes.itTasks}?type=${section.code}`;

    const statCells: [typeof Users, string, number, string][] = [
        [BriefcaseBusiness, 'stat-ico-blue', stats.active, t('service_pages.stat_active')],
        [CheckCircle2, 'stat-ico-sky', stats.completed, t('service_pages.stat_completed')],
        [Users, 'stat-ico-orange', stats.providers, t('service_pages.stat_providers')],
        ...(stats.resumes !== null
            ? [[FileUser, 'stat-ico-violet', stats.resumes, t('service_pages.stat_resumes')] as [typeof Users, string, number, string]]
            : []),
    ];

    return (
        <PublicLayout title={section.title} description={section.lead}>
            <div className="container" style={{ paddingBlock: '32px 96px' }}>
                {/* ── Заголовок ── */}
                <div className="service-hero">
                    <span className="service-hero-ico" aria-hidden>
                        <Icon />
                    </span>
                    <div style={{ minWidth: 0 }}>
                        <Link href={routes.itTasks} className="eyebrow">
                            {t('service_pages.eyebrow')}
                        </Link>
                        <h1 className="t-section">{section.title}</h1>
                        <p className="t-lead">{section.lead}</p>
                    </div>
                    <Link href={routes.itTaskCreate} className="btn btn-primary btn-lg service-hero-cta">
                        <PlusCircle aria-hidden className="size-5" /> {t('it_tasks.post_task')}
                    </Link>
                </div>

                {/* ── Счётчики ── */}
                <div
                    className="stats-band-card service-stats"
                    style={{ gridTemplateColumns: `repeat(${statCells.length}, 1fr)` }}
                >
                    {statCells.map(([StatIcon, tone, value, label]) => (
                        <div key={label} className="stat-cell">
                            <span className={cn('stat-ico', tone)}>
                                <StatIcon aria-hidden className="size-5" />
                            </span>
                            <div style={{ minWidth: 0 }}>
                                <div className="stat-cell-num">
                                    <CountUp value={value} />
                                </div>
                                <div className="stat-cell-label">{label}</div>
                            </div>
                        </div>
                    ))}
                </div>

                {/* ── Что можно заказать и что входит ── */}
                <div className={cn('service-about', kinds.length > 0 && 'service-about--split')}>
                    <div className="card service-offers">
                        <h2 className="t-h3">{t('service_pages.offers_title')}</h2>
                        <ul>
                            {section.offers.map((offer) => (
                                <li key={offer}>
                                    <CheckCircle2 aria-hidden className="size-4" />
                                    {offer}
                                </li>
                            ))}
                        </ul>
                    </div>

                    {kinds.length > 0 && (
                        <div className="card service-kinds">
                            <h2 className="t-h3">{t('service_pages.kinds_title')}</h2>
                            <div className="service-kinds-list">
                                {kinds.map((k) => (
                                    <Link key={k.href} href={k.href} className="service-kind">
                                        <span>{k.label}</span>
                                        <span className="muted">
                                            {k.kind === 'resumes'
                                                ? tChoice('resume.found', k.count)
                                                : tChoice('it_tasks.found', k.count)}
                                        </span>
                                    </Link>
                                ))}
                            </div>
                        </div>
                    )}
                </div>

                {/* ── Открытые задачи ── */}
                <section className="service-block">
                    <div className="section-bar">
                        <h2>{t('service_pages.tasks_title')}</h2>
                        <Link href={feed} className="section-bar-link">
                            {t('service_pages.tasks_all')} <ArrowRight aria-hidden className="go-arrow size-4" />
                        </Link>
                    </div>
                    {tasks.length > 0 ? (
                        <div className="grid grid-3">
                            {tasks.map((row) => (
                                <TaskCard key={row.id} row={row} />
                            ))}
                        </div>
                    ) : (
                        <div className="card empty">
                            <p className="t-body">{t('service_pages.tasks_empty')}</p>
                            <Link href={routes.itTaskCreate} className="btn btn-primary mt-24">
                                {t('it_tasks.post_task')}
                            </Link>
                        </div>
                    )}
                </section>

                {/* ── Резюме (HR) ── */}
                {resumes.length > 0 && (
                    <section className="service-block">
                        <div className="section-bar">
                            <h2>{t('service_pages.resumes_title')}</h2>
                            <Link href={routes.resumes} className="section-bar-link">
                                {t('service_pages.resumes_all')} <ArrowRight aria-hidden className="go-arrow size-4" />
                            </Link>
                        </div>
                        <div className="grid grid-3">
                            {resumes.map((row) => (
                                <ResumeCard key={row.id} row={row} fields={resumeFields} />
                            ))}
                        </div>
                    </section>
                )}

                {/* ── Исполнители ── */}
                <section className="service-block">
                    <div className="section-bar">
                        <h2>{t('service_pages.providers_title')}</h2>
                    </div>
                    {providers.length > 0 ? (
                        <div className="supplier-grid">
                            {providers.map((p) => (
                                <Link key={p.slug} href={routes.company(p.slug)} className="supplier-card">
                                    <span className="supplier-head">
                                        <span className="listing-logo logo-48">
                                            {p.logo ? <img src={p.logo} alt="" loading="lazy" /> : p.initials}
                                        </span>
                                        <VerificationBadge level={p.verification_level} />
                                    </span>
                                    <span className="supplier-name">{p.name}</span>
                                    <span className="supplier-meta">
                                        {[p.specializations.join(', '), p.city].filter(Boolean).join(' · ')}
                                    </span>
                                    <span className="supplier-facts">
                                        <span className="listing-rating">
                                            <Star aria-hidden className="size-3.5" /> <b>{p.rating.toFixed(1)}</b>
                                        </span>
                                    </span>
                                </Link>
                            ))}
                        </div>
                    ) : (
                        <div className="card empty">
                            <p className="t-body muted">{t('service_pages.providers_empty')}</p>
                        </div>
                    )}
                </section>

                {/* ── Уже выполнено ── */}
                {completed.length > 0 && (
                    <section className="service-block">
                        <div className="section-bar">
                            <h2>{t('service_pages.completed_title')}</h2>
                            <Link href={`${feed}&done=1`} className="section-bar-link">
                                {t('service_pages.tasks_all')} <ArrowRight aria-hidden className="go-arrow size-4" />
                            </Link>
                        </div>
                        <div className="grid grid-3">
                            {completed.map((row) => (
                                <TaskCard key={row.id} row={row} />
                            ))}
                        </div>
                    </section>
                )}

                {/* ── Призыв ── */}
                <section className="service-block">
                    <div className="cta-band">
                        <h2 className="t-h1">{t('service_pages.cta_title')}</h2>
                        <p className="t-lead">{t('service_pages.cta_text')}</p>
                        <Link
                            href={routes.itTaskCreate}
                            className="btn btn-lg"
                            style={{ background: '#fff', color: 'var(--primary-700)' }}
                        >
                            {t('it_tasks.post_task')}
                        </Link>
                    </div>
                </section>

                {/* ── Другие направления ── */}
                <section className="service-block">
                    <h2 className="t-h3" style={{ marginBottom: 14 }}>
                        {t('service_pages.others_title')}
                    </h2>
                    <div className="service-others">
                        {pages
                            .filter((p) => p.slug !== section.slug)
                            .map((p) => {
                                const PageIcon = SERVICE_PAGE_ICONS[p.slug] ?? BriefcaseBusiness;

                                return (
                                    <Link key={p.slug} href={routes.serviceSection(p.slug)} className="service-other">
                                        <PageIcon aria-hidden className="size-5" />
                                        {p.title}
                                    </Link>
                                );
                            })}
                    </div>
                </section>
            </div>
        </PublicLayout>
    );
}
