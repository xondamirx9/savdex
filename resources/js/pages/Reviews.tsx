import { ArrowLeft, ArrowRight, MessageSquare, PenLine } from 'lucide-react';
import { ReviewCard, type FeedReview } from '@/components/ReviewCard';
import { Stars } from '@/components/Stars';
import { Link } from '@/components/ui/Link';
import { PublicLayout } from '@/layouts/PublicLayout';
import { numberLocale, t, tChoice } from '@/lib/i18n';
import { routes } from '@/routes';

type FeedType = 'all' | 'platform' | 'company';

interface Summary {
    count: number;
    average: number | null;
    stars: { star: number; count: number }[];
    criteria: { key: string; label: string; average: number | null }[];
}

/** Оценка с одним знаком после запятой по правилам языка страницы. */
function score(value: number): string {
    return value.toLocaleString(numberLocale(), { minimumFractionDigits: 1, maximumFractionDigits: 1 });
}

function pageHref(type: FeedType, page: number): string {
    const query = new URLSearchParams();

    if (type !== 'all') {
        query.set('type', type);
    }

    if (page > 1) {
        query.set('page', String(page));
    }

    const qs = query.toString();

    return qs ? `${routes.reviews}?${qs}` : routes.reviews;
}

/**
 * «Все отзывы»: о площадке и о компаниях.
 *
 * Сверху — оценка SavdEx по отзывам пользователей: средняя, разбивка
 * по звёздам и по сторонам работы. Ниже — лента с вкладками и
 * постраничным выводом. Всё из базы: отзывы пишут сами пользователи,
 * каждый проходит проверку.
 */
export default function Reviews({
    summary,
    counts,
    type,
    reviews,
    page,
    pages,
}: {
    summary: Summary;
    counts: Record<FeedType, number>;
    type: FeedType;
    reviews: FeedReview[];
    page: number;
    pages: number;
}) {
    const most = Math.max(1, ...summary.stars.map((s) => s.count));
    const tabs: FeedType[] = ['all', 'platform', 'company'];

    return (
        <PublicLayout title={t('seo.reviews_title')} description={t('seo.reviews_description')}>
            <div className="container">
                <nav aria-label={t('companies_page.crumbs')} style={{ padding: '20px 0 4px' }}>
                    <ol className="row t-sm muted" style={{ gap: 8, flexWrap: 'wrap' }}>
                        <li>
                            <Link href={routes.home}>{t('companies_page.home')}</Link>
                        </li>
                        <li aria-hidden="true">/</li>
                        <li aria-current="page" style={{ color: 'var(--text)' }}>
                            {t('reviews_page.title')}
                        </li>
                    </ol>
                </nav>

                <div className="section-head-left" style={{ padding: '8px 0 0', marginBottom: 28 }}>
                    <h1 className="t-section">{t('reviews_page.title')}</h1>
                    <p className="t-lead">{t('reviews_page.lead')}</p>
                </div>

                <section className="card" style={{ marginBottom: 32 }}>
                    <div
                        style={{
                            display: 'grid',
                            gap: 24,
                            gridTemplateColumns: 'repeat(auto-fit, minmax(240px, 1fr))',
                            alignItems: 'start',
                        }}
                    >
                        <div className="stack-8">
                            <span className="eyebrow">{t('reviews_page.platform_rating')}</span>
                            {summary.average !== null ? (
                                <>
                                    <div className="row" style={{ gap: 12, alignItems: 'center' }}>
                                        <b style={{ fontSize: 44, lineHeight: 1 }}>{score(summary.average)}</b>
                                        <Stars value={Math.round(summary.average)} size={20} />
                                    </div>
                                    <p className="t-sm muted">{tChoice('reviews_page.based_on', summary.count)}</p>
                                </>
                            ) : (
                                <p className="t-sm muted">{t('reviews_page.no_rating')}</p>
                            )}
                            <div>
                                <Link href={routes.reviewsNew} className="btn btn-primary">
                                    <PenLine aria-hidden className="size-4" /> {t('reviews_page.leave')}
                                </Link>
                            </div>
                        </div>

                        {summary.count > 0 && (
                            <div className="stack-8" aria-label={t('reviews_page.platform_rating')}>
                                {summary.stars.map((s) => (
                                    <div key={s.star} className="row t-sm" style={{ gap: 10, alignItems: 'center' }}>
                                        <span style={{ width: 12 }}>{s.star}</span>
                                        <span
                                            aria-hidden
                                            style={{
                                                flex: 1,
                                                height: 8,
                                                borderRadius: 4,
                                                background: 'var(--border)',
                                                overflow: 'hidden',
                                            }}
                                        >
                                            <span
                                                style={{
                                                    display: 'block',
                                                    height: '100%',
                                                    width: `${(s.count / most) * 100}%`,
                                                    background: 'var(--warning)',
                                                }}
                                            />
                                        </span>
                                        <span className="muted" style={{ width: 28, textAlign: 'right' }}>
                                            {s.count}
                                        </span>
                                    </div>
                                ))}
                            </div>
                        )}

                        {summary.criteria.some((c) => c.average !== null) && (
                            <div className="stack-8">
                                <span className="t-sm muted">{t('reviews_page.criteria')}</span>
                                {summary.criteria.map((c) => (
                                    <div
                                        key={c.key}
                                        className="row t-sm"
                                        style={{ gap: 10, alignItems: 'center', justifyContent: 'space-between' }}
                                    >
                                        <span>{c.label}</span>
                                        <b>{c.average !== null ? score(c.average) : '—'}</b>
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>
                </section>

                <nav className="tabs" aria-label={t('reviews_page.title')} style={{ marginBottom: 20 }}>
                    {tabs.map((key) => (
                        <Link
                            key={key}
                            href={pageHref(key, 1)}
                            className="tab"
                            aria-current={key === type ? 'page' : undefined}
                            aria-selected={key === type}
                            preserveScroll
                        >
                            {t(`reviews_page.tabs.${key}`)} · {counts[key]}
                        </Link>
                    ))}
                </nav>

                {type === 'company' && (
                    <p className="t-sm muted" style={{ margin: '-4px 0 20px' }}>
                        {t('reviews_page.company_note')}
                    </p>
                )}

                {reviews.length === 0 ? (
                    <div className="card empty">
                        <div className="empty-icon">
                            <MessageSquare aria-hidden className="size-7" />
                        </div>
                        <p className="t-h4">{t('reviews_page.empty')}</p>
                    </div>
                ) : (
                    <div className="review-grid">
                        {reviews.map((r) => (
                            <ReviewCard key={`${r.kind}-${r.id}`} review={r} />
                        ))}
                    </div>
                )}

                {pages > 1 && (
                    <nav
                        className="row"
                        style={{ gap: 12, justifyContent: 'center', alignItems: 'center', margin: '32px 0 48px' }}
                        aria-label={t('reviews_page.page_of', { current: page, total: pages })}
                    >
                        {page > 1 && (
                            <Link href={pageHref(type, page - 1)} className="btn btn-secondary">
                                <ArrowLeft aria-hidden className="size-4" /> {t('reviews_page.prev')}
                            </Link>
                        )}
                        <span className="t-sm muted">{t('reviews_page.page_of', { current: page, total: pages })}</span>
                        {page < pages && (
                            <Link href={pageHref(type, page + 1)} className="btn btn-secondary">
                                {t('reviews_page.next')} <ArrowRight aria-hidden className="size-4" />
                            </Link>
                        )}
                    </nav>
                )}
                <div style={{ height: 48 }} />
            </div>
        </PublicLayout>
    );
}
