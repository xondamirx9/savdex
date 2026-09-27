import { useForm } from '@inertiajs/react';
import { CircleCheck, Clock, TriangleAlert } from 'lucide-react';
import { StarPicker } from '@/components/Stars';
import { Link } from '@/components/ui/Link';
import { PublicLayout } from '@/layouts/PublicLayout';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';

interface MyReview {
    rating: number;
    body: string;
    status: 'moderation' | 'published' | 'hidden';
    note: string | null;
    [criterion: string]: number | string | null;
}

/**
 * «Оцените SavdEx» — отзыв пользователя о самой площадке.
 *
 * Один на пользователя: если отзыв уже есть, форма открывается с ним
 * и показывает, на какой он стадии. Правка отправляет его на проверку
 * заново. Ссылку на эту страницу можно рассылать: гостя сначала
 * попросят войти, а потом вернут сюда.
 */
export default function Leave({
    review,
    blocked,
    criteria,
    minBody,
}: {
    review: MyReview | null;
    /** Почему отзыв оставить нельзя; null — можно */
    blocked: string | null;
    criteria: Record<string, string>;
    minBody: number;
}) {
    const form = useForm<Record<string, number | string>>({
        rating: review?.rating ?? 0,
        body: review?.body ?? '',
        ...Object.fromEntries(Object.keys(criteria).map((k) => [k, Number(review?.[k] ?? 0)])),
    });

    function submit(e: React.FormEvent) {
        e.preventDefault();
        form.post(routes.reviewsNew, { preserveScroll: true });
    }

    const status = review?.status;

    return (
        <PublicLayout title={t('platform_reviews.title')}>
            <div className="container" style={{ maxWidth: 720, padding: '32px 16px 64px' }}>
                <h1 className="t-section">{t('platform_reviews.title')}</h1>
                <p className="t-lead" style={{ marginBottom: 24 }}>
                    {t('platform_reviews.lead')}
                </p>

                {status === 'moderation' && (
                    <div className="alert alert-info" style={{ marginBottom: 20 }}>
                        <Clock aria-hidden className="size-4" /> <span>{t('platform_reviews.status_moderation')}</span>
                    </div>
                )}
                {status === 'published' && (
                    <div className="alert alert-success" style={{ marginBottom: 20 }}>
                        <CircleCheck aria-hidden className="size-4" /> <span>{t('platform_reviews.status_published')}</span>
                    </div>
                )}
                {status === 'hidden' && (
                    <div className="alert alert-warning" style={{ marginBottom: 20 }}>
                        <TriangleAlert aria-hidden className="size-4" />
                        <span>
                            {t('platform_reviews.status_hidden')}
                            {review?.note && (
                                <>
                                    <br />
                                    <b>{t('platform_reviews.moderator_note')}:</b> {review.note}
                                </>
                            )}
                        </span>
                    </div>
                )}

                {blocked !== null ? (
                    <div className="alert alert-warning">
                        <TriangleAlert aria-hidden className="size-4" /> <span>{blocked}</span>
                    </div>
                ) : (
                    <form onSubmit={submit} className="card">
                        <div className="stack-16">
                            <StarPicker
                                label={t('platform_reviews.overall')}
                                value={Number(form.data.rating)}
                                onChange={(v) => form.setData('rating', v)}
                            />
                            {form.errors.rating && (
                                <p className="hint" style={{ color: 'var(--danger)' }}>
                                    {form.errors.rating}
                                </p>
                            )}

                            <p className="t-xs muted" style={{ marginBottom: -8 }}>
                                {t('platform_reviews.criteria_hint')}
                            </p>
                            {Object.entries(criteria).map(([key, label]) => (
                                <StarPicker
                                    key={key}
                                    label={label}
                                    value={Number(form.data[key] ?? 0)}
                                    onChange={(v) => form.setData(key, v)}
                                />
                            ))}

                            <div className="field">
                                <label className="label" htmlFor="platform-review-body">
                                    {t('platform_reviews.body')} <span className="req">*</span>
                                </label>
                                <textarea
                                    id="platform-review-body"
                                    className="textarea"
                                    style={{ minHeight: 140 }}
                                    minLength={minBody}
                                    maxLength={2000}
                                    value={String(form.data.body)}
                                    onChange={(e) => form.setData('body', e.target.value)}
                                    placeholder={t('platform_reviews.placeholder')}
                                />
                                {form.errors.body && (
                                    <p className="hint" style={{ color: 'var(--danger)' }}>
                                        {form.errors.body}
                                    </p>
                                )}
                            </div>

                            <div className="row" style={{ gap: 10, flexWrap: 'wrap' }}>
                                <button className="btn btn-primary" disabled={form.processing}>
                                    {form.processing
                                        ? t('platform_reviews.sending')
                                        : review
                                          ? t('platform_reviews.update')
                                          : t('platform_reviews.send')}
                                </button>
                                <Link href={routes.reviews} className="btn btn-secondary">
                                    {t('platform_reviews.all_reviews')}
                                </Link>
                            </div>
                        </div>
                    </form>
                )}
            </div>
        </PublicLayout>
    );
}
