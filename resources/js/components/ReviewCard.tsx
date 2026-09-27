import { Stars } from '@/components/Stars';
import { Link } from '@/components/ui/Link';
import { t } from '@/lib/i18n';
import { routes } from '@/routes';

/** Отзыв из общей ленты (ReviewFeed): о компании или о самой площадке. */
export interface FeedReview {
    id: number;
    kind: 'company' | 'platform';
    author: string;
    initials: string;
    rating: number;
    body: string;
    when: string;
    company_name: string | null;
    company_slug: string | null;
}

/**
 * Карточка отзыва — одна на главной и на странице «Все отзывы».
 *
 * Под автором — о ком отзыв: ссылка на визитку компании или на отзывы
 * о площадке. Без этой строки отзыв о площадке читался бы как отзыв
 * о компании автора.
 */
export function ReviewCard({ review }: { review: FeedReview }) {
    return (
        <article className="review-card">
            <Stars value={review.rating} />
            <p className="review-body">{review.body}</p>
            <div className="review-foot">
                <span className="avatar-sm" aria-hidden>
                    {review.initials}
                </span>
                <span style={{ minWidth: 0 }}>
                    <b className="t-sm" style={{ display: 'block' }}>
                        {review.author}
                    </b>
                    {review.kind === 'company' && review.company_slug ? (
                        <Link href={routes.company(review.company_slug)} className="review-company">
                            {t('home.reviews_about', { name: review.company_name ?? '' })}
                        </Link>
                    ) : (
                        <Link href={`${routes.reviews}?type=platform`} className="review-company">
                            {t('home.reviews_about_platform')}
                        </Link>
                    )}
                </span>
                <span className="t-xs" style={{ marginLeft: 'auto', flexShrink: 0 }}>
                    {review.when}
                </span>
            </div>
        </article>
    );
}
