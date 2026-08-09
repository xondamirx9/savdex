import { useForm } from '@inertiajs/react';
import { BadgeCheck, MessageSquare, Star } from 'lucide-react';
import { useState } from 'react';

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

/** Пять звёзд: заполненные до оценки включительно. */
function Stars({ value, size = 16 }: { value: number; size?: number }) {
    return (
        <span className="row" style={{ gap: 2 }} aria-label={`Оценка ${value} из 5`}>
            {[1, 2, 3, 4, 5].map((i) => (
                <Star
                    key={i}
                    aria-hidden
                    style={{ width: size, height: size }}
                    fill={i <= value ? 'var(--warning)' : 'none'}
                    color={i <= value ? 'var(--warning)' : 'var(--border-strong)'}
                />
            ))}
        </span>
    );
}

/** Выбор оценки звёздами — то же управление, что и в чтении. */
function StarPicker({
    value,
    onChange,
    label,
}: {
    value: number;
    onChange: (v: number) => void;
    label: string;
}) {
    const [hover, setHover] = useState(0);
    const shown = hover || value;

    return (
        <div className="row" style={{ gap: 12, alignItems: 'center', justifyContent: 'space-between' }}>
            <span className="t-sm">{label}</span>
            <span className="row" style={{ gap: 2 }} onMouseLeave={() => setHover(0)}>
                {[1, 2, 3, 4, 5].map((i) => (
                    <button
                        key={i}
                        type="button"
                        aria-label={`${i} из 5`}
                        onMouseEnter={() => setHover(i)}
                        onClick={() => onChange(i)}
                        style={{ background: 'none', border: 0, padding: 2, cursor: 'pointer', lineHeight: 0 }}
                    >
                        <Star
                            aria-hidden
                            className="size-5"
                            fill={i <= shown ? 'var(--warning)' : 'none'}
                            color={i <= shown ? 'var(--warning)' : 'var(--border-strong)'}
                        />
                    </button>
                ))}
            </span>
        </div>
    );
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
                    Отзывы {reviews.length > 0 && <span className="muted">· {reviews.length}</span>}
                </h2>
                {reviews.length > 0 && (
                    <div className="row" style={{ gap: 8, alignItems: 'center' }}>
                        <Stars value={Math.round(rating)} />
                        <b>{rating.toFixed(1)}</b>
                    </div>
                )}
            </div>

            {blocked === null ? (
                open ? (
                    <form onSubmit={submit} className="card mb-24" style={{ background: 'var(--bg)' }}>
                        <div className="stack-16">
                            <StarPicker
                                label="Общая оценка"
                                value={form.data.rating}
                                onChange={(v) => form.setData('rating', v)}
                            />
                            {form.errors.rating && (
                                <p className="hint" style={{ color: 'var(--danger)' }}>{form.errors.rating}</p>
                            )}

                            {Object.entries(criteria).map(([key, label]) => (
                                <StarPicker
                                    key={key}
                                    label={label}
                                    value={Number(form.data[key] ?? 0)}
                                    onChange={(v) => form.setData(key, v)}
                                />
                            ))}

                            <div className="field">
                                <label className="label" htmlFor="review-body">
                                    Как прошла работа <span className="req">*</span>
                                </label>
                                <textarea
                                    id="review-body"
                                    className="textarea"
                                    style={{ minHeight: 110 }}
                                    value={form.data.body}
                                    onChange={(e) => form.setData('body', e.target.value)}
                                    placeholder="Что заказывали, как договаривались об условиях, уложились ли в сроки"
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
                                <span className="t-sm">Сделка состоялась</span>
                            </label>

                            <div className="row" style={{ gap: 10 }}>
                                <button type="button" className="btn btn-secondary" onClick={() => setOpen(false)}>
                                    Отмена
                                </button>
                                <button className="btn btn-primary" style={{ flex: 1 }} disabled={form.processing}>
                                    {form.processing ? 'Публикуем…' : 'Опубликовать отзыв'}
                                </button>
                            </div>
                        </div>
                    </form>
                ) : (
                    <button className="btn btn-outline btn-block mb-24" onClick={() => setOpen(true)}>
                        <MessageSquare aria-hidden className="size-4" /> Оставить отзыв
                    </button>
                )
            ) : (
                <p className="t-sm muted mb-24">{blocked}</p>
            )}

            {reviews.length === 0 ? (
                <p className="t-sm muted">
                    Отзывов пока нет. Их оставляют только те, кто оплатил раскрытие контактов, — поэтому здесь
                    не бывает отзывов от тех, кто с компанией не работал.
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
                                            <span className="badge badge-verified" title="Сделка подтверждена">
                                                <BadgeCheck aria-hidden className="size-3.5" /> Сделка
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
                                    <div className="t-xs muted">Ответ компании</div>
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
