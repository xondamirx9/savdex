import { Heart } from 'lucide-react';
import { ProductCard, type ProductRow } from '@/components/ProductCard';
import { Link } from '@/components/ui/Link';
import { PublicLayout } from '@/layouts/PublicLayout';
import { t, tChoice } from '@/lib/i18n';
import { routes } from '@/routes';

/**
 * Избранные объявления.
 *
 * Снятые с публикации карточки остаются в списке приглушёнными:
 * молча выкинуть то, что человек сохранял, — значит заставить его
 * гадать, куда оно делось.
 */
export default function Favorites({ items }: { items: ProductRow[] }) {
    return (
        <PublicLayout title={t('favorites.meta_title')}>
            <div className="container" style={{ padding: '32px 0 96px' }}>
                <div className="section-head-left" style={{ marginBottom: 24 }}>
                    <span className="eyebrow">{t('favorites.eyebrow')}</span>
                    <h1 className="t-section">{t('favorites.h1')}</h1>
                </div>

                {items.length === 0 ? (
                    <div className="card empty">
                        <div className="empty-icon">
                            <Heart aria-hidden className="size-7" />
                        </div>
                        <p className="t-h4">{t('favorites.empty_title')}</p>
                        <p className="t-sm muted mt-8" style={{ maxWidth: 420, margin: '8px auto 0' }}>
                            {t('favorites.empty_text')}
                        </p>
                        <Link href={routes.catalog} className="btn btn-primary mt-24">
                            {t('favorites.empty_action')}
                        </Link>
                    </div>
                ) : (
                    <>
                        <p className="t-sm muted" style={{ marginBottom: 16 }}>
                            {tChoice('favorites.count', items.length)}
                        </p>
                        <div className="product-grid">
                            {items.map((row) => (
                                <ProductCard key={row.id} row={row} />
                            ))}
                        </div>
                    </>
                )}
            </div>
        </PublicLayout>
    );
}
