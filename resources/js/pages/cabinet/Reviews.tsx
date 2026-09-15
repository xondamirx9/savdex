import { useForm } from '@inertiajs/react';
import { BadgeCheck, Star, TriangleAlert } from 'lucide-react';
import { useState } from 'react';
import { BarRow, Empty, Panel, Stars } from '@/components/cabinet';
import { CabinetLayout } from '@/layouts/CabinetLayout';
import { t, tChoice } from '@/lib/i18n';

interface Row {
    id: number;
    author: string | null;
    initials: string | null;
    verified: number;
    rating: number;
    body: string;
    deal_confirmed: boolean;
    listing: string | null;
    reply: string | null;
    dispute_status: string | null;
    moderator_note: string | null;
    when: string;
}

interface Summary {
    average: number;
    total: number;
    /** Список, а не объект: числовые ключи объекта JS пересортирует */
    distribution: { star: number; count: number }[];
    criteria: { label: string; value: number | null }[];
}

export default function Reviews({ reviews, summary }: { reviews: Row[]; summary: Summary | null }) {
    const [replying, setReplying] = useState<number | null>(null);
    const [disputing, setDisputing] = useState<number | null>(null);
    const reply = useForm({ reply: '' });
    const dispute = useForm({ reason: '' });

    if (!summary) {
        return (
            <CabinetLayout title={t('cabinet.reviews.title')} heading={t('cabinet.reviews.title')}>
                <Empty
                    icon={Star}
                    title={t('cabinet.reviews.empty_title')}
                    text={t('cabinet.reviews.empty_text')}
                />
            </CabinetLayout>
        );
    }

    const maxCount = Math.max(...summary.distribution.map((d) => d.count), 1);

    return (
        <CabinetLayout
            title={t('cabinet.reviews.title')}
            heading={t('cabinet.reviews.title')}
            subheading={t('cabinet.reviews.summary', { average: summary.average, reviews: tChoice('cabinet.reviews.reviews_count', summary.total) })}
        >
            <div className="grid grid-2 grid-tight" style={{ marginBottom: 24 }}>
                <div className="card">
                    <div className="row" style={{ gap: 20, alignItems: 'center' }}>
                        <div className="center">
                            <div className="rating-big">{summary.average}</div>
                            <div style={{ display: 'flex', justifyContent: 'center', marginTop: 4 }}>
                                <Stars value={summary.average} />
                            </div>
                            <p className="t-caption muted mt-8">{t('cabinet.reviews.total', { count: summary.total })}</p>
                        </div>
                        <div style={{ flex: 1 }}>
                            {/* Нули показываем: пропущенная строка «2★» читается
                                как отсутствие данных, а это осмысленный ноль */}
                            {summary.distribution.map(({ star, count }) => (
                                <div key={star} className="bar-row" style={{ gridTemplateColumns: '32px 1fr 34px', padding: '4px 0' }}>
                                    <span className="t-sm">{star}★</span>
                                    <div className="bar-track">
                                        <div className="bar-fill" style={{ width: `${(count / maxCount) * 100}%` }} />
                                    </div>
                                    <span className="bar-val t-sm">{count}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>

                <Panel title={t('cabinet.reviews.criteria')}>
                    {summary.criteria.map((c) => (
                        <BarRow
                            key={c.label}
                            label={c.label}
                            value={c.value ?? 0}
                            max={5}
                            suffix={c.value === null ? '' : ''}
                        />
                    ))}
                </Panel>
            </div>

            <div className="stack-16">
                {reviews.map((r) => (
                    <article key={r.id} className="card">
                        <div className="row-between wrap" style={{ gap: 12 }}>
                            <div className="row" style={{ gap: 10 }}>
                                <span className="listing-logo logo-32">{r.initials}</span>
                                <span>
                                    <b>{r.author}</b>{' '}
                                    {r.deal_confirmed && (
                                        <span className="badge badge-verified">
                                            <BadgeCheck aria-hidden className="size-3.5" /> {t('cabinet.reviews.confirmed_deal')}
                                        </span>
                                    )}
                                    <br />
                                    <span className="t-caption muted">
                                        {r.when}
                                        {r.listing && ` · ${r.listing}`}
                                    </span>
                                </span>
                            </div>
                            <Stars value={r.rating} />
                        </div>

                        <p className="t-body mt-16">{r.body}</p>

                        {r.reply && (
                            <div className="card card--pad-sm mt-16" style={{ background: 'var(--bg)', border: 'none' }}>
                                <p className="t-caption muted" style={{ marginBottom: 6 }}>
                                        {t('cabinet.reviews.your_answer')}
                                </p>
                                <p className="t-sm">{r.reply}</p>
                            </div>
                        )}

                        {replying === r.id ? (
                            <div className="mt-16">
                                <textarea
                                    className="textarea"
                                    style={{ minHeight: 90 }}
                                    autoFocus
                                    value={reply.data.reply}
                                    onChange={(e) => reply.setData('reply', e.target.value)}
                                    placeholder={t('cabinet.reviews.answer_placeholder')}
                                />
                                {reply.errors.reply && (
                                    <p className="hint" style={{ color: 'var(--danger)' }}>
                                        {reply.errors.reply}
                                    </p>
                                )}
                                <div className="row mt-12" style={{ gap: 10 }}>
                                    <button
                                        className="btn btn-primary btn-sm"
                                        disabled={reply.processing}
                                        onClick={() =>
                                            reply.post(`/cabinet/reviews/${r.id}/reply`, {
                                                preserveScroll: true,
                                                onSuccess: () => setReplying(null),
                                            })
                                        }
                                    >
                                                {t('cabinet.reviews.publish_answer')}
                                    </button>
                                    <button className="btn btn-ghost btn-sm" onClick={() => setReplying(null)}>
                                                {t('common.cancel')}
                                    </button>
                                </div>
                            </div>
                        ) : disputing === r.id ? (
                            <div className="mt-16">
                                <textarea
                                    className="textarea"
                                    style={{ minHeight: 90 }}
                                    autoFocus
                                    value={dispute.data.reason}
                                    onChange={(e) => dispute.setData('reason', e.target.value)}
                                    placeholder={t('cabinet.reviews.dispute_placeholder')}
                                />
                                {dispute.errors.reason && (
                                    <p className="hint" style={{ color: 'var(--danger)' }}>
                                        {dispute.errors.reason}
                                    </p>
                                )}
                                <div className="row mt-12" style={{ gap: 10 }}>
                                    <button
                                        className="btn btn-primary btn-sm"
                                        disabled={dispute.processing}
                                        onClick={() =>
                                            dispute.post(`/cabinet/reviews/${r.id}/dispute`, {
                                                preserveScroll: true,
                                                onSuccess: () => setDisputing(null),
                                            })
                                        }
                                    >
                                                {t('cabinet.reviews.send_to_moderator')}
                                    </button>
                                    <button className="btn btn-ghost btn-sm" onClick={() => setDisputing(null)}>
                                                {t('common.cancel')}
                                    </button>
                                </div>
                            </div>
                        ) : (
                            <div className="row mt-16" style={{ gap: 8 }}>
                                {!r.reply && (
                                    <button
                                        className="btn btn-secondary btn-sm"
                                        onClick={() => {
                                            setReplying(r.id);
                                            reply.setData('reply', '');
                                        }}
                                    >
                                            {t('cabinet.reviews.answer')}
                                    </button>
                                )}
                                {r.dispute_status === 'pending' ? (
                                    <span className="badge badge-neutral">{t('cabinet.reviews.under_review')}</span>
                                ) : r.dispute_status === 'declined' ? (
                                    <span className="badge badge-warning">{t('cabinet.reviews.dispute_rejected')}</span>
                                ) : (
                                    <button
                                        className="btn btn-ghost btn-sm"
                                        onClick={() => {
                                            setDisputing(r.id);
                                            dispute.setData('reason', '');
                                        }}
                                    >
                                        <TriangleAlert aria-hidden className="size-4" /> {t('cabinet.reviews.dispute')}
                                    </button>
                                )}
                            </div>
                        )}

                        {/* Ответ модератора показывается там же, где подавалось
                            обращение. Искать его в уведомлениях, которые давно
                            пролистали, никто не станет — а это ответ на жалобу
                            компании, и он должен быть на виду */}
                        {r.moderator_note && (
                            <div className="alert alert-warning mt-16">
                                <TriangleAlert aria-hidden className="size-5" />
                                <div>
                                    <b>{t('cabinet.reviews.moderator_decision')}</b>
                                    <p className="t-sm mt-8">{r.moderator_note}</p>
                                </div>
                            </div>
                        )}
                    </article>
                ))}
            </div>

            <p className="t-sm muted mt-24">
                {t('cabinet.reviews.no_delete')}
            </p>
        </CabinetLayout>
    );
}
