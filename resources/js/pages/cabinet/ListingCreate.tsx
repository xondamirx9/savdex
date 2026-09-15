import { PublicLayout } from '@/layouts/PublicLayout';
import { t } from '@/lib/i18n';

export default function ListingCreate() {
    return (
        <PublicLayout title={t('cabinet.listing_create.title')}>
            <div className="container" style={{ paddingBlock: '32px 96px' }}>
                <h1 className="t-h1">{t('cabinet.listing_create.title')}</h1>
                <div className="card mt-24">
                    <p className="muted">{t('cabinet.listing_create.text')}</p>
                </div>
            </div>
        </PublicLayout>
    );
}
