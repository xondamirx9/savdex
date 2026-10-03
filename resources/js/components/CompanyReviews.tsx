import { useForm } from '@inertiajs/react';
import { BadgeCheck, MessageSquare } from 'lucide-react';
import { useState } from 'react';
import { StarPicker, Stars } from '@/components/Stars';
import { formatDecimal, t } from '@/lib/i18n';

export interface CompanyReview {
    id: number;
    author: string;
    initials: string;
    rating: number;
    body: string;
    deal_confirmed: boolean;
    reply: string | null;
    when: string;
}

/**
 * Отзывы на визитке компании.
 *
 * Форма показывается только тем, кто вправе писать; остальным на её
 * месте — причина. Объяснить «отзыв можно оставить после раскрытия
 * контактов» нужно до того, как человек напишет текст, а не после.
 */
export function CompanyReviews({
    slug,
    reviews,
    blocked,
    criteria,
    rating,
}: {
    slug: string;
    reviews: CompanyReview[];
    /** Причина, по которой отзыв оставить нельзя. null — можно */
    blocked: string | null;
    criteria: Record<string, string>;
    rating: number;
}) {
    const [open, setOpen] = useState(false);

    const form = useForm<{
        rating: number;
        body: string;
        deal_confirmed: boolean;
        [key: string]: number | string | boolean;
    }>({
        rating: 0,
        body: '',
        deal_confirmed: false,
        ...Object.fromEntries(Object.keys(criteria).map((k) => [k, 0])),
    });

    function submit(e: React.FormEvent) {
        e.preventDefault();
        // Неотмеченный критерий — «без оценки» (null), а не 0: правило
        // between:1,5 отклоняло 0, и отзыв не уходил без видимой причины
        form.transform((data) =>
            Object.fromEntries(Object.entries(data).map(([k, v]) => [k, k in criteria && v === 0 ? null : v])) as typeof data,
        );
        form.post(`/company/${slug}/review`, {
            preserveScroll: true,
            onSuccess: () => {
                form.reset();
                setOpen(false);
            },
        });
    }

    return (
        <section className="card" id="reviews">
            <div className="row" style={{ justifyContent: 'space-between', alignItems: 'center', marginBottom: 16 }}>
                <h2 className="t-h3">
                    {t('reviews.title')} {reviews.length > 0 && <span className="muted">· {reviews.length}</span>}
                </h2>
                {reviews.length > 0 && (
                    <div className="row" style={{ gap: 8, alignItems: 'center' }}>
                        <Stars value={Math.round(rating)} />
                        <b>{formatDecimal(rating)}</b>
                    </div>
                )}
            </div>

            {blocked === null ? (
                open ? (
                    <form onSubmit={submit} className="card mb-24" style={{ background: 'var(--bg)' }}>
                        <div className="stack-16">
                            <StarPicker
                                label={t('reviews.overall')}
                                value={form.data.rating}
                                onChange={(v) => form.setData('rating', v)}
                            />
                            {form.errors.rating && (
                                <p className="hint" style={{ color: 'var(--danger)' }}>{form.errors.rating}</p>
                            )}

                            {Object.entries(criteria).map(([key, label]) => (
                                <div key={key}>
                                    <StarPicker
                                        label={label}
                                        value={Number(form.data[key] ?? 0)}
                                        onChange={(v) => form.setData(key, v)}
                                    />
                                    {form.errors[key] && (
                                        <p className="hint" style={{ color: 'var(--danger)' }}>{form.errors[key]}</p>
                                    )}
                                </div>
                            ))}

                            <div className="field">
                                <label className="label" htmlFor="review-body">
                                    {t('reviews.how_it_went')} <span className="req">*</span>
                                </label>
                                <textarea
                                    id="review-body"
                                    className="textarea"
                                    style={{ minHeight: 110 }}
                                    value={form.data.body}
                                    onChange={(e) => form.setData('body', e.target.value)}
                                    placeholder={t('reviews.placeholder')}
                                />
                                {form.errors.body && (
                                    <p className="hint" style={{ color: 'var(--danger)' }}>{form.errors.body}</p>
                                )}
                            </div>

                            <label className="row" style={{ gap: 8, alignItems: 'center', cursor: 'pointer' }}>
                                <input
                                    type="checkbox"
                                    checked={form.data.deal_confirmed}
                                    onChange={(e) => form.setData('deal_confirmed', e.target.checked)}
                                />
                                <span className="t-sm">{t('reviews.deal_done')}</span>
                            </label>

                            <div className="row" style={{ gap: 10 }}>
                                <button type="button" className="btn btn-secondary" onClick={() => setOpen(false)}>
                                    {t('common.cancel')}
                                </button>
                                <button className="btn btn-primary" style={{ flex: 1 }} disabled={form.processing}>
                                    {form.processing ? t('reviews.publishing') : t('reviews.publish')}
                                </button>
                            </div>
                        </div>
                    </form>
                ) : (
                    <button className="btn btn-outline btn-block mb-24" onClick={() => setOpen(true)}>
                        <MessageSquare aria-hidden className="size-4" /> {t('reviews.leave')}
                    </button>
                )
            ) : (
                <p className="t-sm muted mb-24">{blocked}</p>
            )}

            {reviews.length === 0 ? (
                <p className="t-sm muted">
                    {t('reviews.empty')}
                </p>
            ) : (
                <div className="stack-16">
                    {reviews.map((r) => (
                        <article key={r.id} className="card" style={{ background: 'var(--bg)' }}>
                            <div className="row" style={{ gap: 12, alignItems: 'center', marginBottom: 8 }}>
                                <span className="avatar-sm">{r.initials}</span>
                                <div style={{ flex: 1 }}>
                                    <div className="row" style={{ gap: 8, alignItems: 'center' }}>
                                        <b className="t-sm">{r.author}</b>
                                        {r.deal_confirmed && (
                                            <span className="badge badge-verified" title={t('reviews.deal_confirmed')}>
                                                <BadgeCheck aria-hidden className="size-3.5" /> {t('reviews.deal')}
                                            </span>
                                        )}
                                    </div>
                                    <div className="t-xs muted">{r.when}</div>
                                </div>
                                <Stars value={r.rating} />
                            </div>

                            <p className="t-sm">{r.body}</p>

                            {r.reply && (
                                <div
                                    className="mt-12"
                                    style={{ paddingLeft: 12, borderLeft: '2px solid var(--border-strong)' }}
                                >
                                    <div className="t-xs muted">{t('reviews.answer')}</div>
                                    <p className="t-sm">{r.reply}</p>
                                </div>
                            )}
                        </article>
                    ))}
                </div>
            )}
        </section>
    );
}
